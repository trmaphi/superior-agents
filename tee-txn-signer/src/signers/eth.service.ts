import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ethers, JsonRpcProvider, Wallet, TransactionRequest } from 'ethers';

@Injectable()
export class EthService {
  private readonly provider: JsonRpcProvider;
  private nonce: number | null = null;
  private readonly wallet: Wallet;

  constructor(private configService: ConfigService) {
    const rpcUrl = this.configService.get<string>('ETHEREUM_RPC_URL');
    if (!rpcUrl) {
      throw new Error('ETHEREUM_RPC_URL not set in environment');
    }
    this.provider = new JsonRpcProvider(rpcUrl);
    
    const privateKey = this.configService.get<string>('ETH_PRIVATE_KEY');
    if (!privateKey) {
      throw new Error('ETH_PRIVATE_KEY not set in environment');
    }
    this.wallet = new Wallet(privateKey, this.provider);
  }

  async useNonce(address: string): Promise<number> {
    if (this.nonce === null) {
      this.nonce = await this.provider.getTransactionCount(address);
      return this.nonce + 1;
    }
    this.nonce += 1;
    return this.nonce;
  }

  async estimateGasPrice(): Promise<string> {
    const feeData = await this.provider.getFeeData();
    return feeData.gasPrice?.toString() ?? '0';
  }

  getWallet(): Wallet {
    return this.wallet;
  }

  getProvider(): JsonRpcProvider {
    return this.provider;
  }

  async buildAndSendTransaction(transaction: TransactionRequest, address: string) {
    const tx: TransactionRequest = {
      to: transaction.to,
      data: transaction.data,
      nonce: await this.useNonce(address),
      gasPrice: await this.estimateGasPrice(),
      gasLimit: transaction.gasLimit ?? await this.provider.estimateGas(transaction)
    };

    const txResponse = await this.wallet.sendTransaction(tx);
    return txResponse.wait();
  }
}
