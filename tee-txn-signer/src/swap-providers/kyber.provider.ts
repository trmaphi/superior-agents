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

export class KyberSwapProvider extends BaseSwapProvider implements ISwapProvider {
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

  private readonly baseUrl = 'https://aggregator-api.kyberswap.com';

  constructor() {
    super(AVAILABLE_PROVIDERS.KYBER);
  }

  async getTokenInfos(searchString: string): Promise<TokenInfo[]> {
    // TODO: Implement token search using KyberSwap API
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
      const response = await axios.get(`${this.baseUrl}/api/v1/routes`, {
        params: {
          tokenIn: params.fromToken.address,
          tokenOut: params.toToken.address,
          amountIn: params.amount.toString(),
          saveGas: 0,
          slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
          deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
          to: params.recipient,
          chainId,
        },
      });

      const { data } = response;
      return {
        inputAmount: new BigNumber(data.inputAmount),
        outputAmount: new BigNumber(data.outputAmount),
        expectedPrice: new BigNumber(data.expectedPrice),
        priceImpact: new BigNumber(data.priceImpact),
        fee: new BigNumber(data.fee || 0),
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
      const response = await axios.post(`${this.baseUrl}/api/v1/route/build`, {
        tokenIn: params.fromToken.address,
        tokenOut: params.toToken.address,
        amountIn: params.amount.toString(),
        saveGas: 0,
        slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
        deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
        to: params.recipient,
        chainId,
      });

      const { data } = response;
      return {
        // @ts-expect-error
        data: data.data,
        to: data.routerAddress,
        value: data.value || '0',
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to execute swap: ${error.message}`);
    }
  }
}
