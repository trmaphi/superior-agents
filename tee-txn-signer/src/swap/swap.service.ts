import { HttpException, Inject, Injectable, Logger } from '@nestjs/common';
import { BigNumber } from 'bignumber.js';
import { SwapRequestDto, QuoteRequestDto } from './dto/swap.dto';
import { ChainId, ISwapProvider, SwapParams, SwapQuote, TokenInfo } from './interfaces/swap.interface';
import { OkxSwapProvider } from '../swap-providers/okx.service';

interface ProviderQuote extends SwapQuote {
  provider: ISwapProvider;
}

@Injectable()
export class SwapService {
  private readonly logger = new Logger(SwapService.name);
  private readonly providers: ISwapProvider[];

  constructor(
    @Inject(OkxSwapProvider)
    private okxService: ISwapProvider,
    // Add other providers here
    // private uniswapProvider: UniswapProvider,
    // private sushiswapProvider: SushiswapProvider,
  ) {
    this.providers = [
      okxService,
      // Add other providers to the array
      // uniswapProvider,
      // sushiswapProvider,
    ];
  }

  async getTokenInfos(searchString: string): Promise<TokenInfo[]> {
    return await this.okxService.getTokenInfos(searchString);
  }

  private createSwapParams(request: SwapRequestDto | QuoteRequestDto): SwapParams {
    return {
      fromToken: {
        address: request.tokenIn,
        chainId: ChainId.ETHEREUM,
        // These will be fetched from token list in a real implementation
        symbol: '',
        decimals: 18,
      },
      toToken: {
        address: request.tokenOut,
        chainId: ChainId.ETHEREUM,
        // These will be fetched from token list in a real implementation
        symbol: '',
        decimals: 18,
      },
      amount: new BigNumber(request.amountIn),
      slippageTolerance: 'slippage' in request ? request.slippage : 0.5,
    };
  }

  private async getQuotesFromProviders(params: SwapParams): Promise<ProviderQuote[]> {
    const quotes: ProviderQuote[] = [];

    await Promise.all(
      this.providers.map(async (provider) => {
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

  async swapTokens(request: SwapRequestDto) {
    try {
      const params = this.createSwapParams(request);
      const quotes = await this.getQuotesFromProviders(params);
      const bestQuote = this.getBestQuote(quotes);

      if (!bestQuote) {
        throw new HttpException('No valid quotes found from any provider', 400);
      }

      this.logger.log(
        `Executing swap with provider ${bestQuote.provider.constructor.name} ` +
        `(output: ${bestQuote.outputAmount.toString()}, ` +
        `impact: ${bestQuote.priceImpact.toString()}%)`
      );

      const result = await bestQuote.provider.executeSwap(params);

      return {
        transactionHash: result.transactionHash,
        status: 'success',
        provider: bestQuote.provider.constructor.name,
        outputAmount: result.actualOutputAmount.toString(),
      };
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
      provider: bestQuote.provider.constructor.name,
      priceImpact: bestQuote.priceImpact.toString(),
      estimatedGas: bestQuote.estimatedGas?.toString(),
    };
  }
}
