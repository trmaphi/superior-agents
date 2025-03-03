import { HttpAdapterHost, NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';
import { BootstrapLogger } from './logger.instance';
import { CatchEverythingFilter } from './exception.filter';

async function bootstrap() {
  const logger = BootstrapLogger();
  const app = await NestFactory.create(AppModule, {
    logger,
  });
  
  const adapterHost = app.get(HttpAdapterHost);

  app.useGlobalPipes(new ValidationPipe());
  app.useGlobalFilters(new CatchEverythingFilter(adapterHost, logger)); 

  const config = new DocumentBuilder()
    .setTitle('Multi DEX Aggerator swap API')
    .setDescription('Swap API support signers for multiple DEX aggerators')
    .setVersion('1.0')
    .build();
  
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('api', app, document);

  await app.listen(3000);
}

bootstrap();
