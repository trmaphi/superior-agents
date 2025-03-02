import { ConsoleLogger } from '@nestjs/common';
import { Logger, PinoLogger } from 'nestjs-pino';

export const BootstrapLogger = (level = 'debug'): Logger | ConsoleLogger => {
  const runningScript = process.env['npm_lifecycle_event']
  if (runningScript === 'start:dev' || runningScript === 'start:debug') {
    return new ConsoleLogger();
  }

  return new Logger(
    new PinoLogger({
      pinoHttp: {
        level,
      },
    }),
    {
      pinoHttp: {
        level,
      },
    },
  );
};