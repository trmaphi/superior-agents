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

  private readonly baseUrl = 'https://open-api.openocean.finance/v3';

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
            inTokenAddress: params.fromToken.address,
            outTokenAddress: params.toToken.address,
            amount: params.amount.toString(),
            gasPrice: '5', // Default gas price, can be made configurable
            slippage: params.slippageTolerance,
            account: params.recipient || '0x0000000000000000000000000000000000000000', // Use zero address if no recipient
          },
        }
      );

      const { data } = response;
      return {
        inputAmount: new BigNumber(data.inAmount),
        outputAmount: new BigNumber(data.outAmount),
        expectedPrice: new BigNumber(data.outAmount).dividedBy(new BigNumber(data.inAmount)),
        priceImpact: new BigNumber(data.resPriceImpact || 0),
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
      const response = await axios.get(
        `${this.baseUrl}/${chainId}/swap`,
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
