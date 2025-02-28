import { Controller, Get, Post, Body } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { SwapService } from './swap.service';
import {
  SwapRequestDto,
  SwapResponseDto,
  QuoteRequestDto,
  QuoteResponseDto,
} from './dto/swap.dto';

@ApiTags('swap')
@Controller()
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
