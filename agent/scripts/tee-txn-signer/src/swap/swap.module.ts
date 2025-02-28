import { Module } from '@nestjs/common';
import { SwapController } from './swap.controller';
import { SwapService } from './swap.service';
import { SignersModule } from '../signers/signers.module';
import { OkxSwapProvider } from '../swap-providers/okx.service';

@Module({
  imports: [SignersModule],
  controllers: [SwapController],
  providers: [SwapService, OkxSwapProvider],
  exports: [SwapService, OkxSwapProvider],
})
export class SwapModule {}
