import { BigNumber } from 'bignumber.js';
import axios from 'axios';
import {
  ChainId,
  ISwapProvider,
  SwapParams,
  SwapQuote,
  TokenInfo,
  UnsignedSwapTransaction,
} from '../swap/interfaces/swap.interface';
import { BaseSwapProvider } from './base-swap.provider';
import { AVAILABLE_PROVIDERS } from './constants';
import { HttpException } from '@nestjs/common';
import * as LossLessJson from 'lossless-json';
import { Logger } from '@nestjs/common';

export class KyberSwapProvider extends BaseSwapProvider implements ISwapProvider {
  private readonly logger = new Logger(KyberSwapProvider.name)
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

  async isInit(): Promise<boolean> {
    return true;
  }



  async isSwapSupported(fromToken: TokenInfo, toToken: TokenInfo): Promise<boolean> {
    return this.validateChainId(fromToken, toToken);
  }

  async _getRoute(params: SwapParams): Promise<any> {
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

      return data
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

  async getSwapQuote(params: SwapParams): Promise<SwapQuote> {
    this.validateSwapParams(params);

    const data = await this._getRoute(params);
    const routeSummary = data.data.routeSummary;
    let fee = BigNumber(0);
    if (routeSummary.extraFee) {
      fee = routeSummary.extraFee.isInBps 
        ? new BigNumber(routeSummary.extraFee.feeAmount).dividedBy(10000) // Convert basis points to decimal
        : new BigNumber(routeSummary.extraFee.feeAmount)
    }
    
    return {
      inputAmount: new BigNumber(routeSummary.amountIn),
      outputAmount: new BigNumber(routeSummary.amountOut),
      expectedPrice: new BigNumber(routeSummary.amountOutUsd).dividedBy(new BigNumber(routeSummary.amountInUsd)),
      fee: fee,
      estimatedGas: new BigNumber(routeSummary.gas),
    };
  }

  async getUnsignedTransaction(params: SwapParams): Promise<UnsignedSwapTransaction> {
    this.validateSwapParams(params);

    const chainName = this.chainIdChainNameMap[params.fromToken.chainId];
    if (!chainName) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }
    const routeData = await this._getRoute(params);
    const body = {
      sender: params.recipient,
      recipient: params.recipient,
      deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
      slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
      // enableGasEstimation: true,
      ignoreCappedSlippage: true,
      routeSummary: routeData.data.routeSummary
    };

    try {
      const response = await axios.post(`${this.baseUrl}/${chainName}/api/v1/route/build`, body, {
        headers: {
          'Content-Type': 'application/json',
          'x-client-id': this.xClientId,
        },
        validateStatus: (number) => {
          if (number != 200) {
            this.logger.log(`kyber status provider return status ${number}`);
          }

          return true
        }
      });

      const data = response.data;
      if (response.status != 200) {
        throw new HttpException(LossLessJson.stringify(data), response.status);
      }

      if (data.code !== 0) {
        throw new Error(data.message || 'Failed to build swap transaction');
      }  

      return {
        to: data.data.routerAddress,
        data: data.data.data,
        value: '0', // For ERC20 to ERC20 swaps
        gasLimit: data.data.gas
      };
    } catch (error) {
      if (error instanceof HttpException) {
        throw error;
      }
      // @ts-expect-error
      throw new Error(`Failed to execute swap: ${error.message}`);
    }
  }
}
