import { BigNumber } from 'bignumber.js';

export enum ChainId {
  // Mainnets
  ETHEREUM = 'evm-1',
  SOL = 'sol',
}

export interface ChainInfo {
  id: ChainId;
  name: string;
  nativeCurrency: {
    name: string;
    symbol: string;
    decimals: number;
  };
  rpcUrl?: string;
}

export interface TokenInfo {
  address: string;
  symbol?: string;
  decimals: number;
  chainId: ChainId;
}

export interface SwapQuote {
  inputAmount: BigNumber;
  outputAmount: BigNumber;
  expectedPrice: BigNumber;
  priceImpact: BigNumber;
  fee: BigNumber;
  estimatedGas?: BigNumber;
}

export interface SwapParams {
  fromToken: TokenInfo;
  toToken: TokenInfo;
  amount: BigNumber;
  slippageTolerance: number; // in percentage (e.g., 0.5 for 0.5%)
  deadline?: number; // timestamp in seconds
  recipient?: string; // if different from sender
}

export interface SwapResult {
  transactionHash: string;
  actualInputAmount: BigNumber;
  actualOutputAmount: BigNumber;
  fee: BigNumber;
  timestamp: number;
}

export interface ISwapProvider {
  /**
   * Get the chains supported by this provider
   */
  readonly supportedChains: ChainId[];

  getName(): string;

  getSupportedChains(): ChainId[];

  isInit(): Promise<boolean>;

  /**
   * Get token information for a given address or a search string
   */
  getTokenInfos(searchString: string): Promise<TokenInfo[]>;

  /**
   * Check if a token pair is supported for swapping
   */
  isSwapSupported(fromToken: TokenInfo, toToken: TokenInfo): Promise<boolean>;

  /**
   * Get a quote for a swap without executing it
   */
  getSwapQuote(params: SwapParams): Promise<SwapQuote>;

  /**
   * Execute a swap transaction
   */
  executeSwap(params: SwapParams): Promise<SwapResult>;

  /**
   * Get the balance of a specific token for an address
   */
  getTokenBalance(token: TokenInfo, address: string): Promise<BigNumber>;

  /**
   * Get the native balance (ETH, SOL, etc.) for an address
   */
  getNativeBalance(address: string): Promise<BigNumber>;
}
