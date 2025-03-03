import { Controller, Get, Post, Body, Patch, Param, Delete, Inject } from '@nestjs/common';
import { EthService } from '../signers/eth.service';
import { SolanaService } from '../signers/sol.service';

@Controller('addresses')
export class AddressesController {
  constructor(
    @Inject(EthService)
    private readonly ethService: EthService,
    @Inject(SolanaService)
    private readonly solService: SolanaService,
  ) {}

  @Get()
  findMe() {
    return {
      'evm': this.ethService.getWallet().address,
      'sol': this.solService.getPublicKey(),
    }
  }
}
