import { BigNumber } from 'bignumber.js';
import axios from 'axios';
import {
  ChainId,
  ISwapProvider,
  SwapParams,
  SwapQuote,
  SwapResult,
  TokenInfo,
} from '../swap/interfaces/swap.interface';
import { BaseSwapProvider } from './base-swap.provider';

export class OpenOceanProvider extends BaseSwapProvider implements ISwapProvider {
  readonly supportedChains = [
    ChainId.ETHEREUM,
  ];

  // https://docs.openocean.finance/dev/developer-resources/supported-chains
  private readonly chainIdChainCodeMap: { [key in ChainId]?: string } = {
    [ChainId.ETHEREUM]: 'eth',
  };

  private readonly baseUrl = 'https://api.openocean.finance/v4';

  constructor() {
    super('OpenOcean');
  }

  async getTokenInfos(searchString: string): Promise<TokenInfo[]> {
    // TODO: Implement token search using OpenOcean API
    throw new Error('Method not implemented.');
  }

  async getTokenBalance(token: TokenInfo, address: string): Promise<BigNumber> {
    // TODO: Implement token balance check
    throw new Error('Method not implemented.');
  }

  async getNativeBalance(address: string): Promise<BigNumber> {
    // TODO: Implement native balance check
    throw new Error('Method not implemented.');
  }

  async isSwapSupported(fromToken: TokenInfo, toToken: TokenInfo): Promise<boolean> {
    return this.validateChainId(fromToken, toToken);
  }

  async getSwapQuote(params: SwapParams): Promise<SwapQuote> {
    this.validateSwapParams(params);

    const chainCode = this.chainIdChainCodeMap[params.fromToken.chainId];
    if (!chainCode) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      const response = await axios.get(
        `${this.baseUrl}/${chainCode}/quote`,
        {
          params: {
            inTokenAddress: params.fromToken.address,
            outTokenAddress: params.toToken.address,
            amount: params.amount.toString(),
            gasPrice: '5', // Default gas price, can be made configurable
            slippage: params.slippageTolerance,
            account: params.recipient || '0x0000000000000000000000000000000000000000', // Use zero address if no recipient
          },
        }
      );

      const { data } = response.data; // API v4 wraps response in data object
      return {
        inputAmount: new BigNumber(data.inAmount),
        outputAmount: new BigNumber(data.outAmount),
        expectedPrice: new BigNumber(data.outAmount).dividedBy(new BigNumber(data.inAmount)),
        priceImpact: new BigNumber(data.price_impact?.replace('%', '') || 0).dividedBy(100), // Convert percentage string to decimal
        fee: new BigNumber(0), // Fee not provided in v4 response
        estimatedGas: new BigNumber(data.estimatedGas),
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to get swap quote: ${error.message}`);
    }
  }

  async executeSwap(params: SwapParams): Promise<SwapResult> {
    this.validateSwapParams(params);

    const chainCode = this.chainIdChainCodeMap[params.fromToken.chainId];
    if (!chainCode) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      const response = await axios.get(
        `${this.baseUrl}/${chainCode}/swap`,
        {
          params: {
            inTokenAddress: params.fromToken.address,
            outTokenAddress: params.toToken.address,
            amount: params.amount.toString(),
            from: params.recipient,
            slippage: params.slippageTolerance,
            gasPrice: '5', // Default gas price, can be made configurable
            deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
          },
        }
      );

      const { data } = response;
      return {
        // @ts-expect-error
        data: data.data,
        to: data.to,
        value: data.value || '0',
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to execute swap: ${error.message}`);
    }
  }
}
