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
  ];

  // https://docs.kyberswap.com/kyberswap-solutions/kyberswap-aggregator/aggregator-api-specification/evm-swaps
  // Check identifiers
  private readonly chainIdChainNameMap: { [key in ChainId]?: string } = {
    [ChainId.ETHEREUM]: 'ethereum',
  };

  private readonly baseUrl = 'https://aggregator-api.kyberswap.com';
  private readonly xClientId = 'superior-swap-api';

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

    const chainName = this.chainIdChainNameMap[params.fromToken.chainId];
    if (!chainName) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      // https://docs.kyberswap.com/kyberswap-solutions/kyberswap-aggregator/aggregator-api-specification/evm-swaps
      const response = await axios.get(`${this.baseUrl}/${chainName}/api/v1/routes`, {
        headers: {
          'x-client-id': this.xClientId,
        },
        params: {
          tokenIn: params.fromToken.address,
          tokenOut: params.toToken.address,
          amountIn: params.amount.toString(),
          gasInclude: true,
          slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
          deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
          to: params.recipient,
        },
      });

      const { data } = response;
      
      // Check if response is successful
      if (data.code !== 0) {
        throw new Error(data.message || 'Unknown error occurred');
      }

      const routeSummary = data.data.routeSummary;
      
      return {
        inputAmount: new BigNumber(routeSummary.amountIn),
        outputAmount: new BigNumber(routeSummary.amountOut),
        expectedPrice: new BigNumber(routeSummary.amountOutUsd).dividedBy(new BigNumber(routeSummary.amountInUsd)),
        priceImpact: new BigNumber(0), // Not provided in the API response
        fee: routeSummary.extraFee ? new BigNumber(routeSummary.extraFee.feeAmount) : new BigNumber(0),
        estimatedGas: new BigNumber(routeSummary.gas),
      };
    } catch (error: any) {
      // Handle specific error codes
      if (error.response?.data) {
        const { code, message } = error.response.data;
        switch (code) {
          case 4221:
            throw new Error('WETH token not found on this chain');
          case 4001:
            throw new Error('Invalid query parameters');
          case 4002:
            throw new Error('Invalid request body');
          case 4005:
            throw new Error('Fee amount exceeds input amount');
          default:
            throw new Error(message || 'Failed to get swap quote');
        }
      }
      
      throw new Error(`Failed to get swap quote: ${error.message}`);
    }
  }

  async executeSwap(params: SwapParams): Promise<SwapResult> {
    this.validateSwapParams(params);

    const chainName = this.chainIdChainNameMap[params.fromToken.chainId];
    if (!chainName) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    try {
      const response = await axios.post(`${this.baseUrl}/${chainName}/api/v1/route/build`, {
        headers: {
          'x-client-id': this.xClientId,
        },
        body: {
          tokenIn: params.fromToken.address,
          tokenOut: params.toToken.address,
          amountIn: params.amount.toString(),
          saveGas: 0,
          slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
          deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
          to: params.recipient,
        }
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
