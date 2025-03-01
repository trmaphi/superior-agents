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
import { AVAILABLE_PROVIDERS } from './constants';

export class OneInchV6Provider extends BaseSwapProvider implements ISwapProvider {
  readonly supportedChains = [
    ChainId.ETHEREUM,
    ChainId.BSC,
    ChainId.POLYGON,
    ChainId.ARBITRUM,
    ChainId.OPTIMISM,
    ChainId.AVALANCHE,
  ];

  private readonly chainIdMap = {
    [ChainId.ETHEREUM]: 1,
    [ChainId.BSC]: 56,
    [ChainId.POLYGON]: 137,
    [ChainId.ARBITRUM]: 42161,
    [ChainId.OPTIMISM]: 10,
    [ChainId.AVALANCHE]: 43114,
  };

  private readonly baseUrl = 'https://api.1inch.dev/swap/v6.0';
  private readonly apiKey: string;

  constructor(apiKey: string) {
    super(AVAILABLE_PROVIDERS.ONEINCH_V6);
    this.apiKey = apiKey;
  }

  private getHeaders() {
    return {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Accept': 'application/json',
      },
    };
  }

  async getTokenInfos(searchString: string): Promise<TokenInfo[]> {
    // TODO: Implement token search using 1inch API
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

    // @ts-expect-error
    const chainId = this.chainIdMap[params.fromToken.chainId];
    if (!chainId) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      const response = await axios.get(
        `${this.baseUrl}/${chainId}/quote`,
        {
          params: {
            src: params.fromToken.address, // Source token address
            dst: params.toToken.address, // Destination token address
            amount: params.amount.toString(), // Amount of source tokens to swap in minimal divisible units
          },
          ...this.getHeaders(),
        }
      );

      const { data } = response;
      return {
        inputAmount: new BigNumber(data.fromTokenAmount),
        outputAmount: new BigNumber(data.toTokenAmount),
        expectedPrice: new BigNumber(data.toTokenAmount).dividedBy(new BigNumber(data.fromTokenAmount)),
        priceImpact: new BigNumber(data.estimatedPriceImpact || 0),
        fee: new BigNumber(0), // 1inch doesn't explicitly return fee information
        estimatedGas: new BigNumber(data.estimatedGas || 0),
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to get swap quote: ${error.message}`);
    }
  }

  async executeSwap(params: SwapParams): Promise<SwapResult> {
    this.validateSwapParams(params);

    // @ts-expect-error
    const chainId = this.chainIdMap[params.fromToken.chainId];
    if (!chainId) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      const response = await axios.get(
        `${this.baseUrl}/${chainId}/swap`,
        {
          params: {
            src: params.fromToken.address, // Source token address
            dst: params.toToken.address, // Destination token address
            amount: params.amount.toString(), // Amount of source tokens to swap in minimal divisible units
            from: params.recipient, // Address of user initiating swap
            slippage: params.slippageTolerance.toString(), // Maximum acceptable slippage percentage for the swap
            ...(params.deadline ? { deadline: params.deadline.toString() } : {}),
          },
          ...this.getHeaders(),
        }
      );

      const { data } = response;
      return {
        // @ts-expect-error
        data: data.tx.data,
        to: data.tx.to,
        value: data.tx.value || '0',
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to execute swap: ${error.message}`);
    }
  }
}
