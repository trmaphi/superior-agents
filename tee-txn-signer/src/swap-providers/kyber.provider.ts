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

  async isInit(): Promise<boolean> {
    return true;
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
    
    return {
      inputAmount: new BigNumber(routeSummary.amountIn),
      outputAmount: new BigNumber(routeSummary.amountOut),
      expectedPrice: new BigNumber(routeSummary.amountOutUsd).dividedBy(new BigNumber(routeSummary.amountInUsd)),
      priceImpact: new BigNumber(0), // Not provided in the API response
      fee: routeSummary.extraFee ? new BigNumber(routeSummary.extraFee.feeAmount) : new BigNumber(0),
      estimatedGas: new BigNumber(routeSummary.gas),
    };
  }

  async getUnsignedTransaction(params: SwapParams): Promise<UnsignedSwapTransaction> {
    this.validateSwapParams(params);

    const chainName = this.chainIdChainNameMap[params.fromToken.chainId];
    if (!chainName) {
      throw new Error(`Unsupported chain ID: ${params.fromToken.chainId}`);
    }

    // {
    //   "code": 0,
    //   "message": "successfully",
    //   "data": {
    //     "routerAddress": "0x6131B5fae19EA4f9D964eAc0408E4408b66337b5",
    //     "routeSummary": {
    //       "tokenIn": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
    //       "amountIn": "1000000000000000000",
    //       "amountInUsd": "1668.95",
    //       "tokenInMarketPriceAvailable": false,
    //       "tokenOut": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
    //       "amountOut": "1666243758",
    //       "amountOutUsd": "1665.9071767608839",
    //       "tokenOutMarketPriceAvailable": false,
    //       "gas": "253000",
    //       "gasPrice": "181968304449",
    //       "gasUsd": "0.06491355324609177",
    //       "extraFee": {
    //         "feeAmount": "10",
    //         "chargeFeeBy": "currency_out",
    //         "isInBps": true,
    //         "feeReceiver": "0x0513c794bC2c65C6f374a86D6ad04425e32Df22e"
    //       },
    //       "route": [
    //         [
    //           {
    //             "pool": "0x4b543e89351faa242cb0172b2da0cdb52db699b4",
    //             "tokenIn": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
    //             "tokenOut": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
    //             "limitReturnAmount": "0",
    //             "swapAmount": "1000000000000000000",
    //             "amountOut": "1667911669",
    //             "exchange": "dodo",
    //             "poolLength": 2,
    //             "poolType": "dodo",
    //             "poolExtra": {
    //               "type": "DPP",
    //               "dodoV1SellHelper": "0xdfaf9584f5d229a9dbe5978523317820a8897c5a",
    //               "baseToken": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
    //               "quoteToken": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
    //             },
    //             "extra": {
    //               "amountIn": "1000000000000000000",
    //               "swapSide": "BUY",
    //               "filledOrders": [
    //                 {
    //                   "allowedSenders": "0x0000000000000000000000000000000000000000",
    //                   "feeAmount": "0",
    //                   "feeRecipient": "0x0000000000000000000000000000000000000000",
    //                   "filledMakingAmount": "950000",
    //                   "filledTakingAmount": "1000000000000000000",
    //                   "getMakerAmount": "f4a215c30000000000000000000000000000000000000000000000000000000011e1a3000000000000000000000000000000000000000000000000111e75953102eec1a0",
    //                   "getTakerAmount": "296637bf0000000000000000000000000000000000000000000000000000000011e1a3000000000000000000000000000000000000000000000000111e75953102eec1a0",
    //                   "interaction": "",
    //                   "isFallback": false,
    //                   "maker": "0xda060fd9ae5b23cebf8abcb2d19fab152a419d61",
    //                   "makerAsset": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
    //                   "makerAssetData": "",
    //                   "makerTokenFeePercent": 0,
    //                   "makingAmount": "300000000",
    //                   "orderId": 9886,
    //                   "permit": "",
    //                   "predicate": "961d5b1e000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000002000000000000000000000000227b0c196ea8db17a665ea6824d972a64202e936000000000000000000000000227b0c196ea8db17a665ea6824d972a64202e9360000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000c00000000000000000000000000000000000000000000000000000000000000044cf6fc6e3000000000000000000000000da060fd9ae5b23cebf8abcb2d19fab152a419d61000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002463592c2b000000000000000000000000000000000000000000000000000000006453683300000000000000000000000000000000000000000000000000000000",
    //                   "receiver": "0xda060fd9ae5b23cebf8abcb2d19fab152a419d61",
    //                   "salt": "202362243813858115557509104206720377774",
    //                   "signature": "8fb37c9b14d9ccd7709ccc8289860c24580b69f1ab0e905a7d8c20e2ae5e45c570d33324990afb94a445246872545c5eaf9712b164a90ac7f97502d91a7c27001b",
    //                   "takerAsset": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270",
    //                   "takerAssetData": "",
    //                   "takingAmount": "315789473684210500000"
    //                 }
    //               ]
    //             }
    //           }
    //         ]
    //       ]
    //     }
    //   }
    // }
    const routeData = await this._getRoute(params);
    const body = LossLessJson.stringify({
      sender: params.recipient,
      recipient: params.recipient,
      deadline: params.deadline || Math.floor(Date.now() / 1000) + 1200, // 20 minutes from now if not specified
      slippageTolerance: params.slippageTolerance * 100, // Convert to basis points
      enableGasEstimation: true,
      ignoreCappedSlippage: true,
      routeSummary: routeData.data.routeSummary
    });
    try {
      const response = await fetch(`${this.baseUrl}/${chainName}/api/v1/route/build`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-client-id': this.xClientId,
        },
        body: body
      });

      const data = await response.json();
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
