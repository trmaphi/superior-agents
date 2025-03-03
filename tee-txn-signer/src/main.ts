import { HttpAdapterHost, NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';
import { BootstrapLogger } from './logger.instance';
import { CatchEverythingFilter } from './exception.filter';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, {
    logger: BootstrapLogger(),
  });
  
  const { httpAdapter } = app.get(HttpAdapterHost);
  // @ts-expect-error
  app.useGlobalFilters(new CatchEverythingFilter(httpAdapter)); 
  app.useGlobalPipes(new ValidationPipe());

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
