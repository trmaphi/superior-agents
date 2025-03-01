import { Logger, PinoLogger } from 'nestjs-pino';

export const BootstrapLogger = (level = 'debug'): Logger => {
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