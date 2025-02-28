import { Controller, Get, Post, Body, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { SwapService } from './swap.service';
import {
  SwapRequestDto,
  SwapResponseDto,
  QuoteRequestDto,
  QuoteResponseDto,
} from './dto/swap.dto';
import { TokenInfoDto } from './dto/tokeninfo.dto';
import { TokenInfo } from './interfaces/swap.interface';

@ApiTags('swap')
@Controller('/api/v1')
export class SwapController {
  constructor(private readonly swapService: SwapService) {}

  @Get('health')
  @ApiOperation({ summary: 'Health check endpoint' })
  @ApiResponse({ status: 200, description: 'Service is healthy' })
  async healthCheck() {
    return {
      status: 'healthy',
    };
  }

  @Get('tokenInfos')
  @ApiOperation({ summary: 'Get token infos' })
  @ApiResponse({ status: 200 })
  async getTokenInfos(@Query('q') q: string): Promise<TokenInfo[]> {
    return this.swapService.getTokenInfos(q);
  }

  @Post('swap')
  @ApiOperation({ summary: 'Swap tokens using 1inch API' })
  @ApiResponse({ status: 200, type: SwapResponseDto })
  async swapTokens(@Body() request: SwapRequestDto): Promise<SwapResponseDto> {
    return this.swapService.swapTokens(request);
  }

  @Post('quote')
  @ApiOperation({ summary: 'Get quote for token swap' })
  @ApiResponse({ status: 200, type: QuoteResponseDto })
  async getQuote(@Body() request: QuoteRequestDto): Promise<QuoteResponseDto> {
    return this.swapService.getQuote(request);
  }
}
