import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { SwapModule } from './swap/swap.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
    }),
    SwapModule,
  ],
})
export class AppModule {}
