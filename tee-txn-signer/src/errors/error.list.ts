import { HttpException } from "@nestjs/common";

export class NoValidQuote extends HttpException {
    static status = 400;
    static desc = "No valid quotes found from any provider";
    constructor() {
        super(NoValidQuote.desc, NoValidQuote.status);
    }
}