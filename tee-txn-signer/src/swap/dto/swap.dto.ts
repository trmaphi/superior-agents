import { ApiProperty } from '@nestjs/swagger';
import { IsString, IsNumber, IsOptional } from 'class-validator';

export class SwapRequestDto {
  @ApiProperty({ description: 'Chain Id of the input token, currently only support sol' })
  chainId!: string;

  @ApiProperty({ description: 'Input token address' })
  @IsString()
  tokenIn!: string;

  @ApiProperty({ description: 'Chain Id of the output token, currently only support sol' })
  @IsString()
  chainOut!: string;

  @ApiProperty({ description: 'Output token address' })
  @IsString()
  tokenOut!: string;

  @ApiProperty({ description: 'Input amount in smallest denomination' })
  @IsString()
  amountIn!: string;

  @ApiProperty({ description: 'Slippage tolerance in percentage', default: 0.5 })
  @IsNumber()
  @IsOptional()
  slippage: number = 0.5;
}

export class SwapResponseDto {
  @ApiProperty()
  @IsString()
  @IsOptional()
  transactionHash?: string;

  @ApiProperty()
  @IsString()
  status!: string;

  @ApiProperty()
  @IsString()
  @IsOptional()
  error?: string;
}

export class QuoteRequestDto {
  @ApiProperty({ description: 'Chain Id of the input token, currently only support sol' })
  chainIn!: string;

  @ApiProperty({ description: 'Input token address' })
  @IsString()
  tokenIn!: string;

  @ApiProperty({ description: 'Chain Id of the output token, currently only support sol' })
  chainOut!: string;

  @ApiProperty({ description: 'Output token address' })
  @IsString()
  tokenOut!: string;

  @ApiProperty({ description: 'Input amount in smallest denomination' })
  @IsString()
  amountIn!: string;
}

export class QuoteResponseDto {
  @ApiProperty({ description: 'Output amount in smallest denomination' })
  @IsString()
  amountOut!: string;
}
