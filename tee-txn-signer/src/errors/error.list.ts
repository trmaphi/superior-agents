import { HttpException, HttpExceptionOptions } from "@nestjs/common";

export class NoValidQuote extends HttpException {
    static status = 400;
    static desc = "No valid quotes found from any provider";
    constructor(options: HttpExceptionOptions) {
        super(NoValidQuote.desc, NoValidQuote.status, options);
    }
}

export class ExecutionReveted extends HttpException {
    static status = 400;
    static desc = "Execution reverted";
    constructor(options: HttpExceptionOptions) {
        super(ExecutionReveted.desc, ExecutionReveted.status, options);
    }
}