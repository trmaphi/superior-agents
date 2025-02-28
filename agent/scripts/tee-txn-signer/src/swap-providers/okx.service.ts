import { Injectable } from '@nestjs/common';
import { BigNumber } from 'bignumber.js';
import axios from 'axios';
import {
  ChainId,
  SwapParams,
  SwapQuote,
  SwapResult,
  TokenInfo,
} from '../swap/interfaces/swap.interface';
import { BaseSwapProvider } from './base-swap.provider';

@Injectable()
export class OkxSwapProvider extends BaseSwapProvider {
  readonly supportedChains = [ChainId.SOL];
  private readonly baseUrl = 'https://www.okx.com';
  private readonly apiKey: string;
  private readonly apiSecret: string;
  private readonly passphrase: string;

  constructor() {
    super('OKX');
    // These should be injected via configuration
    this.apiKey = process.env.OKX_API_KEY || '';
    this.apiSecret = process.env.OKX_API_SECRET || '';
    this.passphrase = process.env.OKX_PASSPHRASE || '';
  }

  private getHeaders() {
    const timestamp = new Date().toISOString();
    const signature = this.generateSignature(timestamp);

    return {
      'OK-ACCESS-KEY': this.apiKey,
      'OK-ACCESS-SIGN': signature,
      'OK-ACCESS-TIMESTAMP': timestamp,
      'OK-ACCESS-PASSPHRASE': this.passphrase,
    };
  }

  private generateSignature(timestamp: string): string {
    // Implement signature generation according to OKX documentation
    return ''; // Placeholder
  }

  async getTokenBalance(token: TokenInfo, address: string): Promise<BigNumber> {
    try {
      const response = await axios.get(
        `${this.baseUrl}/api/v5/account/balance`,
        {
          headers: this.getHeaders(),
          params: {
            address,
            token: token.symbol,
          },
        },
      );
      return new BigNumber(response.data.data[0].available);
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to get token balance: ${error.message}`);
    }
  }

  async getNativeBalance(address: string): Promise<BigNumber> {
    return this.getTokenBalance(
      {
        address: 'SOL',
        symbol: 'SOL',
        decimals: 9,
        chainId: ChainId.SOL,
      },
      address,
    );
  }

  async executeSwap(params: SwapParams): Promise<SwapResult> {
    this.validateSwapParams(params);

    try {
      const response = await axios.post(
        `${this.baseUrl}/api/v5/dex/swap`,
        {
          chainId: 'sol',
          fromTokenAddress: params.fromToken.address,
          toTokenAddress: params.toToken.address,
          amount: params.amount.toString(),
          slippage: params.slippageTolerance,
          deadline: this.getDeadline(params),
          recipient: params.recipient,
        },
        { headers: this.getHeaders() },
      );

      const result = response.data.data[0];
      return {
        transactionHash: result.txHash,
        actualInputAmount: new BigNumber(result.fromAmount),
        actualOutputAmount: new BigNumber(result.toAmount),
        fee: new BigNumber(result.fee),
        timestamp: Math.floor(Date.now() / 1000),
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Swap execution failed: ${error.message}`);
    }
  }

  async getSwapQuote(params: SwapParams): Promise<SwapQuote> {
    this.validateSwapParams(params);

    try {
      const response = await axios.get(
        `${this.baseUrl}/api/v5/dex/quote`,
        {
          headers: this.getHeaders(),
          params: {
            chainId: 'sol',
            fromTokenAddress: params.fromToken.address,
            toTokenAddress: params.toToken.address,
            amount: params.amount.toString(),
          },
        },
      );

      const quote = response.data.data[0];
      const inputAmount = new BigNumber(quote.fromAmount);
      const outputAmount = new BigNumber(quote.toAmount);
      const expectedPrice = outputAmount.div(inputAmount);

      return {
        inputAmount,
        outputAmount,
        expectedPrice,
        priceImpact: this.calculatePriceImpact(
          inputAmount,
          outputAmount,
          expectedPrice,
        ),
        fee: new BigNumber(quote.fee),
        estimatedGas: new BigNumber(quote.estimatedGas || 0),
      };
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to get swap quote: ${error.message}`);
    }
  }

  async isSwapSupported(
    fromToken: TokenInfo,
    toToken: TokenInfo,
  ): Promise<boolean> {
    if (!this.validateChainId(fromToken, toToken)) {
      return false;
    }

    try {
      const response = await axios.get(
        `${this.baseUrl}/api/v5/dex/tokens`,
        {
          headers: this.getHeaders(),
          params: { chainId: 'sol' },
        },
      );

      const supportedTokens = response.data.data;
      return (
        supportedTokens.some(
          (token: any) =>
            token.address.toLowerCase() === fromToken.address.toLowerCase(),
        ) &&
        supportedTokens.some(
          (token: any) =>
            token.address.toLowerCase() === toToken.address.toLowerCase(),
        )
      );
    } catch (error) {
      // @ts-expect-error
      throw new Error(`Failed to check swap support: ${error.message}`);
    }
  }
}