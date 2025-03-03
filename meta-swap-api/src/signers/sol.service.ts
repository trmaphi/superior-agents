import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  SystemProgram,
  sendAndConfirmTransaction,
  TransactionInstruction,
} from '@solana/web3.js';
import bs58 from 'bs58';

@Injectable()
export class SolanaService {
  private readonly connection: Connection;
  private readonly keypair: Keypair;

  constructor(private configService: ConfigService) {
    const rpcUrl = this.configService.get<string>('SOLANA_RPC_URL');
    if (!rpcUrl) {
      throw new Error('SOLANA_RPC_URL not set in environment');
    }
    this.connection = new Connection(rpcUrl, 'confirmed');

    const privateKey = this.configService.get<string>('SOLANA_PRIVATE_KEY');
    if (!privateKey) {
      throw new Error('SOLANA_PRIVATE_KEY not set in environment');
    }
    
    // Convert private key from base58 to Uint8Array and create keypair
    const decodedKey = bs58.decode(privateKey);
    this.keypair = Keypair.fromSecretKey(decodedKey);
  }

  getPublicKey(): PublicKey {
    return this.keypair.publicKey;
  }

  async getBalance(publicKey: PublicKey): Promise<number> {
    return this.connection.getBalance(publicKey);
  }

  async buildAndSendTransaction(
    instructions: TransactionInstruction[],
    signers: Keypair[] = [this.keypair],
  ) {
    const latestBlockhash = await this.connection.getLatestBlockhash();
    
    const transaction = new Transaction({
      feePayer: this.keypair.publicKey,
      ...latestBlockhash,
    }).add(...instructions);

    const signature = await sendAndConfirmTransaction(
      this.connection,
      transaction,
      signers,
      {
        commitment: 'confirmed',
      }
    );

    return signature;
  }

  async transferSOL(
    recipientAddress: string,
    amount: number, // in SOL
  ) {
    const recipient = new PublicKey(recipientAddress);
    const lamports = amount * 1e9; // Convert SOL to lamports

    const instruction = SystemProgram.transfer({
      fromPubkey: this.keypair.publicKey,
      toPubkey: recipient,
      lamports,
    });

    return this.buildAndSendTransaction([instruction]);
  }

  async createTokenSwapInstruction(
    tokenSwapProgramId: PublicKey,
    tokenAccountA: PublicKey,
    tokenAccountB: PublicKey,
    poolToken: PublicKey,
    amountIn: number,
    minAmountOut: number,
  ): Promise<TransactionInstruction> {
    // This is a placeholder for the actual swap instruction
    // You'll need to implement this based on the specific DEX or AMM you're using
    // (e.g., Orca, Raydium, or Serum)
    const instruction = new TransactionInstruction({
      programId: tokenSwapProgramId,
      keys: [
        { pubkey: tokenAccountA, isSigner: false, isWritable: true },
        { pubkey: tokenAccountB, isSigner: false, isWritable: true },
        { pubkey: poolToken, isSigner: false, isWritable: true },
        { pubkey: this.keypair.publicKey, isSigner: true, isWritable: false },
      ],
      data: Buffer.from([/* Encoded instruction data */]),
    });

    return instruction;
  }
}
