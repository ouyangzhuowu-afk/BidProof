import { Container } from "@cloudflare/containers";

export class BidProofContainer extends Container {
  defaultPort = 8080;
  requiredPorts = [8080];
  pingEndpoint = "/healthz";
  sleepAfter = "30m";
  enableInternet = true;

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      BIDPROOF_ENV: "production",
      BIDPROOF_ALLOW_TRUSTED_HEADERS: "0",
      BIDPROOF_BOOTSTRAP_TOKEN: env.BIDPROOF_BOOTSTRAP_TOKEN,
    };
  }
}

export default {
  async fetch(request, env) {
    const container = env.BIDPROOF.getByName("singleton");
    await container.startAndWaitForPorts();
    return container.fetch(request);
  },
};
