import { Module } from "@nestjs/common";
import { OkxSwapProvider } from "./okx.service";

@Module({
    providers: [OkxSwapProvider],
    exports: [OkxSwapProvider],
})
export class SwapProvidersModule {}
  