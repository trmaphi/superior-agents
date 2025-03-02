import { HttpException, Inject, Injectable, Logger } from '@nestjs/common';
import { BigNumber } from 'bignumber.js';
import { ethers } from 'ethers';
import { SwapRequestDto, QuoteRequestDto } from './dto/swap.dto';
import { ChainId, ISwapProvider, SwapParams, SwapQuote, TokenInfo } from './interfaces/swap.interface';
import { OkxSwapProvider } from '../swap-providers/okx.provider';
import { KyberSwapProvider } from '../swap-providers/kyber.provider';
import { OneInchV6Provider } from '../swap-providers/1inch.v6.provider';
import { OpenOceanProvider } from '../swap-providers/openfinance.provider';
import { NoValidQuote } from '../errors/error.list';

interface ProviderQuote extends SwapQuote {
  provider: ISwapProvider;
}

const dexScreenChainIdMap = {
  'solana': ChainId.SOL,
  'ethereum': ChainId.ETHEREUM,
}

@Injectable()
export class SwapService {
  private readonly logger = new Logger(SwapService.name);
  private readonly providers: ISwapProvider[];

  constructor(
    @Inject(OkxSwapProvider)
    private okx: ISwapProvider,
    @Inject(KyberSwapProvider)
    private kyber: ISwapProvider,
    @Inject(OneInchV6Provider)
    private oneInchV6: ISwapProvider,
    @Inject(OpenOceanProvider)
    private openOcean: ISwapProvider,
  ) {
    this.providers = [
      okx,
      kyber,
      oneInchV6,
      openOcean,
    ];
  }

  async getTokenInfos(searchString: string): Promise<TokenInfo[]> {
    try {
      const response = await fetch(
        `https://api.dexscreener.com/latest/dex/search?q=${encodeURIComponent(searchString)}`,
      );
      if (!response.ok) {
        throw new Error(`DexScreener API error: ${response.statusText}`);
      }

      const data = await response.json();
      const pairs = data.pairs || [];
      
      // Filter pairs with liquidity over 50k USD
      const highLiquidityPairs = pairs.filter((pair: any) => {
        return pair.liquidity && pair.liquidity.usd >= 50000;
      });

      // Extract unique tokens from high liquidity pairs
      const tokenMap = new Map<string, TokenInfo>();
      highLiquidityPairs.forEach((pair: any) => {
        const baseToken = pair.baseToken;
        const dexScreenChainId = pair.chainId as string;
        if (baseToken && baseToken.address && !tokenMap.has(baseToken.address)) {
          // @ts-expect-error
          const chainId = dexScreenChainIdMap[dexScreenChainId];
          if (chainId) {
            tokenMap.set(baseToken.address, {
              address: baseToken.address,
              symbol: baseToken.symbol,
              decimals: 18, // Most tokens use 18 decimals
              chainId,
            });
          }
        }
      });

      return Array.from(tokenMap.values());
    } catch (error) {
      console.error('Error fetching token info:', error);
      throw error;
    }
  }

  private createSwapParams(request: SwapRequestDto | QuoteRequestDto): SwapParams {
    return {
      fromToken: {
        address: request.tokenIn,
        chainId: request.chainIn as unknown as ChainId,
        decimals: 18,
      },
      toToken: {
        address: request.tokenOut,
        chainId: request.chainOut as unknown as ChainId,
        decimals: 18,
      },
      amount: new BigNumber(request.amountIn),
      slippageTolerance: 'slippage' in request ? request.slippage : 0.5,
    };
  }

  private async getActiveProviders(): Promise<ISwapProvider[]> {
    const activeProviders: ISwapProvider[] = [];
    
    await Promise.all(
      this.providers.map(async (provider) => {
        try {
          const isInit = await provider.isInit();
          if (isInit) {
            activeProviders.push(provider);
          }
        } catch (error) {
          this.logger.warn(
            `Failed to check initialization status for provider ${provider.constructor.name}: ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      })
    );

    return activeProviders;
  }

  private async getQuotesFromProviders(params: SwapParams): Promise<ProviderQuote[]> {
    const quotes: ProviderQuote[] = [];
    const activeProviders = await this.getActiveProviders();

    await Promise.all(
      activeProviders.map(async (provider) => {
        try {
          const isSupported = await provider.isSwapSupported(
            params.fromToken,
            params.toToken
          );

          if (!isSupported) {
            this.logger.debug(
              `Pair not supported by provider ${provider.constructor.name}`
            );
            return;
          }

          const quote = await provider.getSwapQuote(params);
          quotes.push({ ...quote, provider });
        } catch (error) {
          this.logger.warn(
            `Failed to get quote from provider ${provider.constructor.name}: ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      })
    );

    return quotes;
  }

  private getBestQuote(quotes: ProviderQuote[]): ProviderQuote | null {
    if (quotes.length === 0) return null;

    return quotes.reduce((best, current) => {
      // Compare output amounts
      if (current.outputAmount.gt(best.outputAmount)) {
        return current;
      }
      // If output amounts are equal, compare price impact
      if (current.outputAmount.eq(best.outputAmount) && 
          current.priceImpact.lt(best.priceImpact)) {
        return current;
      }
      return best;
    });
  }

  async swapTokensByProvider(provider: string, request: SwapRequestDto) {
    const targetProviders = await this.getActiveProviders();
    let targetProvider: ISwapProvider | null = null;
    for (const checkingProvider of targetProviders) {
      if (checkingProvider.getName() === provider) {
        targetProvider = checkingProvider;
        break;
      }
    }

    if (!targetProvider) {
      throw new Error(`Unsupported provider: ${provider}`);
    }
    
    const params = this.createSwapParams(request);
    const unsignedTx = await targetProvider.getUnsignedTransaction(params);

    // Create provider and wallet
    const ethersProvider = new ethers.JsonRpcProvider(process.env.ETH_RPC_URL || '');
    const wallet = new ethers.Wallet(process.env.ETH_RPC_URL || '', ethersProvider);

    // Create and sign transaction
    const tx = {
      to: unsignedTx.to,
      data: unsignedTx.data,
      value: unsignedTx.value ? ethers.parseEther(unsignedTx.value) : 0,
      gasLimit: unsignedTx.gasLimit ? ethers.toBigInt(unsignedTx.gasLimit) : undefined,
    };

    // Sign and send transaction
    const signedTx = await wallet.sendTransaction(tx);
    const receipt = await signedTx.wait();
    if (!receipt) {
      throw new HttpException('Cannot find transaction receipt', 404);
    }

    return {
      transactionHash: receipt.hash,
      status: receipt.status === 1 ? 'success' : 'failed',
      provider: targetProvider.getName(),
    };
  }

  async swapTokens(request: SwapRequestDto) {
    try {
      const params = this.createSwapParams(request);
      const quotes = await this.getQuotesFromProviders(params);
      const bestQuote = this.getBestQuote(quotes);

      if (!bestQuote) {
        throw new NoValidQuote();
      }

      this.logger.log(
        `Executing swap with provider ${bestQuote.provider.getName()} ` +
        `(output: ${bestQuote.outputAmount.toString()}, ` +
        `impact: ${bestQuote.priceImpact.toString()}%)`
      );

      // Create provider and wallet
      const provider = new ethers.JsonRpcProvider(process.env.ETH_RPC_URL || '');
      const wallet = new ethers.Wallet(process.env.ETH_PRIVATE_KEY || '', provider);
      params.recipient = wallet.address;

      const unsignedTx = await bestQuote.provider.getUnsignedTransaction(params);

      // Create and sign transaction
      const tx = {
        to: unsignedTx.to,
        data: unsignedTx.data,
        value: unsignedTx.value ? ethers.parseEther(unsignedTx.value) : 0,
        gasLimit: unsignedTx.gasLimit ? ethers.toBigInt(unsignedTx.gasLimit) : undefined,
      };

      // Sign and send transaction
      // const signedTx = await wallet.sendTransaction(tx);
      // const receipt = await signedTx.wait();

      // if (!receipt) {
      //   throw new HttpException('Cannot find transaction receipt', 404);
      // }

      // return {
      //   transactionHash: receipt.hash,
      //   status: receipt.status === 1 ? 'success' : 'failed',
      //   provider: bestQuote.provider.getName(),
      // };
      return {
        transactionHash: '',
        status: 'success',
        provider: bestQuote.provider.getName(),
      }
    } catch (error) {
      return {
        status: 'error',
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  async getQuote(request: QuoteRequestDto) {
    const params = this.createSwapParams(request);
    const quotes = await this.getQuotesFromProviders(params);
    const bestQuote = this.getBestQuote(quotes);

    if (!bestQuote) {
      throw new HttpException('No valid quotes found from any provider', 400);
    }

    return {
      amountOut: bestQuote.outputAmount.toString(),
      provider: bestQuote.provider.getName(),
      priceImpact: bestQuote.priceImpact.toString(),
      estimatedGas: bestQuote.estimatedGas?.toString(),
    };
  }

  async getProviders() {
    const activeProviders = await this.getActiveProviders();
    return activeProviders.map(provider => ({
      name: provider.getName(),
      supportedChains: provider.getSupportedChains()
    }));
  }
}
