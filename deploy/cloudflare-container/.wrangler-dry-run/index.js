var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// node_modules/@cloudflare/containers/dist/lib/helpers.js
function generateId(length = 9) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let result = "";
  for (let i = 0; i < length; i++) {
    result += alphabet[bytes[i] % alphabet.length];
  }
  return result;
}
__name(generateId, "generateId");
function parseTimeExpression(timeExpression) {
  if (typeof timeExpression === "number") {
    return timeExpression;
  }
  if (typeof timeExpression === "string") {
    const match = timeExpression.match(/^(\d+)([smh])$/);
    if (!match) {
      throw new Error(`invalid time expression ${timeExpression}`);
    }
    const value = parseInt(match[1]);
    const unit = match[2];
    switch (unit) {
      case "s":
        return value;
      case "m":
        return value * 60;
      case "h":
        return value * 60 * 60;
      default:
        throw new Error(`unknown time unit ${unit}`);
    }
  }
  throw new Error(`invalid type for a time expression: ${typeof timeExpression}`);
}
__name(parseTimeExpression, "parseTimeExpression");

// node_modules/@cloudflare/containers/dist/lib/container.js
import { DurableObject } from "cloudflare:workers";
var NO_CONTAINER_INSTANCE_ERROR = "there is no container instance that can be provided to this durable object";
var RUNTIME_SIGNALLED_ERROR = "runtime signalled the container to exit:";
var UNEXPECTED_EXIT_ERROR = "container exited with unexpected exit code:";
var NOT_LISTENING_ERROR = "the container is not listening";
var CONTAINER_STATE_KEY = "__CF_CONTAINER_STATE";
var MAX_ALARM_RETRIES = 3;
var PING_TIMEOUT_MS = 5e3;
var DEFAULT_SLEEP_AFTER = "10m";
var INSTANCE_POLL_INTERVAL_MS = 300;
var TIMEOUT_TO_GET_CONTAINER_SECONDS = 8;
var TIMEOUT_TO_GET_PORTS = 20;
var TRIES_TO_GET_CONTAINER = Math.ceil(TIMEOUT_TO_GET_CONTAINER_SECONDS * 1e3 / INSTANCE_POLL_INTERVAL_MS);
var TRIES_TO_GET_PORTS = Math.ceil(TIMEOUT_TO_GET_PORTS * 1e3 / INSTANCE_POLL_INTERVAL_MS);
var FALLBACK_PORT_TO_CHECK = 33;
var TEMPORARY_HARDCODED_ATTEMPT_MAX = 6;
var signalToNumbers = {
  SIGINT: 2,
  SIGTERM: 15,
  SIGKILL: 9
};
function isErrorOfType(e, matchingString) {
  const errorString = e instanceof Error ? e.message : String(e);
  return errorString.toLowerCase().includes(matchingString);
}
__name(isErrorOfType, "isErrorOfType");
var isNoInstanceError = /* @__PURE__ */ __name((error) => isErrorOfType(error, NO_CONTAINER_INSTANCE_ERROR), "isNoInstanceError");
var isRuntimeSignalledError = /* @__PURE__ */ __name((error) => isErrorOfType(error, RUNTIME_SIGNALLED_ERROR), "isRuntimeSignalledError");
var isNotListeningError = /* @__PURE__ */ __name((error) => isErrorOfType(error, NOT_LISTENING_ERROR), "isNotListeningError");
var isContainerExitNonZeroError = /* @__PURE__ */ __name((error) => isErrorOfType(error, UNEXPECTED_EXIT_ERROR), "isContainerExitNonZeroError");
function getExitCodeFromError(error) {
  if (!(error instanceof Error)) {
    return null;
  }
  if (isRuntimeSignalledError(error)) {
    return +error.message.toLowerCase().slice(error.message.toLowerCase().indexOf(RUNTIME_SIGNALLED_ERROR) + RUNTIME_SIGNALLED_ERROR.length + 1);
  }
  if (isContainerExitNonZeroError(error)) {
    return +error.message.toLowerCase().slice(error.message.toLowerCase().indexOf(UNEXPECTED_EXIT_ERROR) + UNEXPECTED_EXIT_ERROR.length + 1);
  }
  return null;
}
__name(getExitCodeFromError, "getExitCodeFromError");
function addTimeoutSignal(existingSignal, timeoutMs) {
  const controller = new AbortController();
  if (existingSignal?.aborted) {
    controller.abort();
    return controller.signal;
  }
  existingSignal?.addEventListener("abort", () => controller.abort());
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  controller.signal.addEventListener("abort", () => clearTimeout(timeoutId));
  return controller.signal;
}
__name(addTimeoutSignal, "addTimeoutSignal");
var ContainerState = class {
  static {
    __name(this, "ContainerState");
  }
  storage;
  status;
  constructor(storage) {
    this.storage = storage;
  }
  async setRunning() {
    await this.setStatusAndupdate("running");
  }
  async setHealthy() {
    await this.setStatusAndupdate("healthy");
  }
  async setStopping() {
    await this.setStatusAndupdate("stopping");
  }
  async setStopped() {
    await this.setStatusAndupdate("stopped");
  }
  async setStoppedWithCode(exitCode) {
    this.status = { status: "stopped_with_code", lastChange: Date.now(), exitCode };
    await this.update();
  }
  async getState() {
    if (!this.status) {
      const state = await this.storage.get(CONTAINER_STATE_KEY);
      if (!state) {
        this.status = {
          status: "stopped",
          lastChange: Date.now()
        };
        await this.update();
      } else {
        this.status = state;
      }
    }
    return this.status;
  }
  async setStatusAndupdate(status) {
    this.status = { status, lastChange: Date.now() };
    await this.update();
  }
  async update() {
    if (!this.status)
      throw new Error("status should be init");
    await this.storage.put(CONTAINER_STATE_KEY, this.status);
  }
};
var Container = class extends DurableObject {
  static {
    __name(this, "Container");
  }
  // =========================
  //     Public Attributes
  // =========================
  // Default port for the container (undefined means no default port)
  defaultPort;
  // Required ports that should be checked for availability during container startup
  // Override this in your subclass to specify ports that must be ready
  requiredPorts;
  // Timeout after which the container will sleep if no activity
  // The signal sent to the container by default is a SIGTERM.
  // The container won't get a SIGKILL if this threshold is triggered.
  sleepAfter = DEFAULT_SLEEP_AFTER;
  // Container configuration properties
  // Set these properties directly in your container instance
  envVars = {};
  entrypoint;
  enableInternet = true;
  // =========================
  //     PUBLIC INTERFACE
  // =========================
  constructor(ctx, env, options) {
    super(ctx, env);
    if (ctx.container === void 0) {
      throw new Error("Containers have not been enabled for this Durable Object class. Have you correctly setup your Wrangler config? More info: https://developers.cloudflare.com/containers/get-started/#configuration");
    }
    this.state = new ContainerState(this.ctx.storage);
    this.ctx.blockConcurrencyWhile(async () => {
      this.renewActivityTimeout();
      await this.scheduleNextAlarm();
    });
    this.container = ctx.container;
    if (options) {
      if (options.defaultPort !== void 0)
        this.defaultPort = options.defaultPort;
      if (options.sleepAfter !== void 0)
        this.sleepAfter = options.sleepAfter;
    }
    this.sql`
      CREATE TABLE IF NOT EXISTS container_schedules (
        id TEXT PRIMARY KEY NOT NULL DEFAULT (randomblob(9)),
        callback TEXT NOT NULL,
        payload TEXT,
        type TEXT NOT NULL CHECK(type IN ('scheduled', 'delayed')),
        time INTEGER NOT NULL,
        delayInSeconds INTEGER,
        created_at INTEGER DEFAULT (unixepoch())
      )
    `;
    if (this.container.running) {
      this.monitor = this.container.monitor();
      this.setupMonitorCallbacks();
    }
  }
  /**
   * Gets the current state of the container
   * @returns Promise<State>
   */
  async getState() {
    return { ...await this.state.getState() };
  }
  // ==========================
  //     CONTAINER STARTING
  // ==========================
  /**
   * Start the container if it's not running and set up monitoring
   *
   * This method handles the core container startup process without waiting for ports to be ready.
   * It will automatically retry if the container fails to start, up to maxTries attempts.
   *
   * It's useful when you need to:
   * - Start a container without blocking until a port is available
   * - Initialize a container that doesn't expose ports
   * - Perform custom port availability checks separately
   *
   * The method applies the container configuration from your instance properties by default, but allows
   * overriding these values for this specific startup:
   * - Environment variables (defaults to this.envVars)
   * - Custom entrypoint commands (defaults to this.entrypoint)
   * - Internet access settings (defaults to this.enableInternet)
   *
   * It also sets up monitoring to track container lifecycle events and automatically
   * calls the onStop handler when the container terminates.
   *
   * @example
   * // Basic usage in a custom Container implementation
   * async customInitialize() {
   *   // Start the container without waiting for a port
   *   await this.start();
   *
   *   // Perform additional initialization steps
   *   // that don't require port access
   * }
   *
   * @example
   * // Start with custom configuration
   * await this.start({
   *   envVars: { DEBUG: 'true', NODE_ENV: 'development' },
   *   entrypoint: ['npm', 'run', 'dev'],
   *   enableInternet: false
   * });
   *
   * @param options - Optional configuration to override instance defaults
   * @param waitOptions - Optional wait configuration with abort signal for cancellation
   * @returns A promise that resolves when the container start command has been issued
   * @throws Error if no container context is available or if all start attempts fail
   */
  async start(options, waitOptions) {
    const portToCheck = this.defaultPort ?? (this.requiredPorts ? this.requiredPorts[0] : FALLBACK_PORT_TO_CHECK);
    await this.startContainerIfNotRunning({
      abort: waitOptions?.signal,
      waitInterval: INSTANCE_POLL_INTERVAL_MS,
      retries: TRIES_TO_GET_CONTAINER,
      portToCheck
    }, options);
    this.setupMonitorCallbacks();
    await this.ctx.blockConcurrencyWhile(async () => {
      await this.onStart();
    });
  }
  /**
   * Start the container and wait for ports to be available
   * Based on containers-starter-go implementation
   *
   * This method builds on start() by adding port availability verification:
   * 1. Calls start() to ensure the container is running
   * 2. If no ports are specified and requiredPorts is not set, it uses defaultPort (if set)
   * 3. If no ports can be determined, it calls onStart and renewActivityTimeout immediately
   * 4. For each specified port, it polls until the port is available or maxTries is reached
   * 5. When all ports are available, it triggers onStart and renewActivityTimeout
   *
   * The method prioritizes port sources in this order:
   * 1. Ports specified directly in the method call
   * 2. requiredPorts class property (if set)
   * 3. defaultPort (if neither of the above is specified)
   *
   * @param ports - The ports to wait for (if undefined, uses requiredPorts or defaultPort)
   * @param maxTries - Maximum number of attempts to connect to each port before failing
   * @throws Error if port checks fail after maxTries attempts
   */
  async startAndWaitForPorts(ports, cancellationOptions) {
    let portsToCheck = [];
    if (ports !== void 0) {
      portsToCheck = Array.isArray(ports) ? ports : [ports];
    } else if (this.requiredPorts && this.requiredPorts.length > 0) {
      portsToCheck = [...this.requiredPorts];
    } else if (this.defaultPort !== void 0) {
      portsToCheck = [this.defaultPort];
    }
    const state = await this.state.getState();
    cancellationOptions ??= {};
    let containerGetRetries = cancellationOptions.instanceGetTimeoutMS ? Math.ceil(cancellationOptions.instanceGetTimeoutMS / INSTANCE_POLL_INTERVAL_MS) : TRIES_TO_GET_CONTAINER;
    cancellationOptions ??= {};
    let totalPortReadyTries = cancellationOptions.portReadyTimeoutMS ? Math.ceil(cancellationOptions.portReadyTimeoutMS / INSTANCE_POLL_INTERVAL_MS) : TRIES_TO_GET_PORTS;
    const options = {
      abort: cancellationOptions.abort,
      retries: containerGetRetries,
      waitInterval: cancellationOptions.waitInterval ?? INSTANCE_POLL_INTERVAL_MS,
      portToCheck: portsToCheck[0] ?? FALLBACK_PORT_TO_CHECK
    };
    if (state.status === "healthy" && this.container.running) {
      if (this.container.running && !this.monitor) {
        await this.startContainerIfNotRunning(options);
        this.setupMonitorCallbacks();
      }
      return;
    }
    await this.syncPendingStoppedEvents();
    const abortedSignal = new Promise((res) => {
      options.abort?.addEventListener("abort", () => {
        res(true);
      });
    });
    const triesUsed = await this.startContainerIfNotRunning(options);
    const triesLeft = totalPortReadyTries - triesUsed;
    for (const port of portsToCheck) {
      const tcpPort = this.container.getTcpPort(port);
      let portReady = false;
      for (let i = 0; i < triesLeft && !portReady; i++) {
        try {
          const combinedSignal = addTimeoutSignal(options.abort, PING_TIMEOUT_MS);
          await tcpPort.fetch("http://ping", { signal: combinedSignal });
          portReady = true;
          console.log(`Port ${port} is ready`);
        } catch (e) {
          const errorMessage = e instanceof Error ? e.message : String(e);
          console.warn(`Error checking ${port}: ${errorMessage}`);
          if (!this.container.running) {
            try {
              await this.onError(new Error(`Container crashed while checking for ports, did you setup the entrypoint correctly?`));
            } catch {
            }
            throw e;
          }
          if (i === triesLeft - 1) {
            try {
              await this.onError(`Failed to verify port ${port} is available after ${options.retries} attempts, last error: ${errorMessage}`);
            } catch {
            }
            throw e;
          }
          await Promise.any([
            new Promise((resolve) => setTimeout(resolve, options.waitInterval)),
            abortedSignal
          ]);
          if (options.abort?.aborted) {
            throw new Error("Container request timed out.");
          }
        }
      }
    }
    this.setupMonitorCallbacks();
    await this.ctx.blockConcurrencyWhile(async () => {
      await this.state.setHealthy();
      await this.onStart();
    });
  }
  // =======================
  //     LIFECYCLE HOOKS
  // =======================
  /**
   * Shuts down the container.
   * @param signal - The signal to send to the container (default: 15 for SIGTERM)
   */
  async stop(signal = "SIGTERM") {
    this.container.signal(typeof signal === "string" ? signalToNumbers[signal] : signal);
  }
  /**
   * Destroys the container. It will trigger onError instead of onStop.
   */
  async destroy() {
    await this.container.destroy();
  }
  /**
   * Lifecycle method called when container starts successfully
   * Override this method in subclasses to handle container start events
   */
  onStart() {
  }
  /**
   * Lifecycle method called when container shuts down
   * Override this method in subclasses to handle Container stopped events
   * @param params - Object containing exitCode and reason for the stop
   */
  onStop(_) {
  }
  /**
   * Lifecycle method called when the container is running, and the activity timeout
   * expiration has been reached.
   *
   * If you want to shutdown the container, you should call this.stop() here
   *
   * By default, this method calls `this.stop()`
   */
  async onActivityExpired() {
    if (!this.container.running) {
      return;
    }
    await this.stop();
  }
  /**
   * Error handler for container errors
   * Override this method in subclasses to handle container errors
   * @param error - The error that occurred
   * @returns Can return any value or throw the error
   */
  onError(error) {
    console.error("Container error:", error);
    throw error;
  }
  /**
   * Renew the container's activity timeout
   *
   * Call this method whenever there is activity on the container
   */
  renewActivityTimeout() {
    const timeoutInMs = parseTimeExpression(this.sleepAfter) * 1e3;
    this.sleepAfterMs = Date.now() + timeoutInMs;
  }
  // ==================
  //     SCHEDULING
  // ==================
  /**
   * Schedule a task to be executed in the future
   * @template T Type of the payload data
   * @param when When to execute the task (Date object or number of seconds delay)
   * @param callback Name of the method to call
   * @param payload Data to pass to the callback
   * @returns Schedule object representing the scheduled task
   */
  async schedule(when, callback, payload) {
    const id = generateId(9);
    if (typeof callback !== "string") {
      throw new Error("Callback must be a string (method name)");
    }
    if (typeof this[callback] !== "function") {
      throw new Error(`this.${callback} is not a function`);
    }
    if (when instanceof Date) {
      const timestamp = Math.floor(when.getTime() / 1e3);
      this.sql`
        INSERT OR REPLACE INTO container_schedules (id, callback, payload, type, time)
        VALUES (${id}, ${callback}, ${JSON.stringify(payload)}, 'scheduled', ${timestamp})
      `;
      await this.scheduleNextAlarm();
      return {
        taskId: id,
        callback,
        payload,
        time: timestamp,
        type: "scheduled"
      };
    }
    if (typeof when === "number") {
      const time = Math.floor(Date.now() / 1e3 + when);
      this.sql`
        INSERT OR REPLACE INTO container_schedules (id, callback, payload, type, delayInSeconds, time)
        VALUES (${id}, ${callback}, ${JSON.stringify(payload)}, 'delayed', ${when}, ${time})
      `;
      await this.scheduleNextAlarm();
      return {
        taskId: id,
        callback,
        payload,
        delayInSeconds: when,
        time,
        type: "delayed"
      };
    }
    throw new Error("Invalid schedule type. 'when' must be a Date or number of seconds");
  }
  // ============
  //     HTTP
  // ============
  /**
   * Send a request to the container (HTTP or WebSocket) using standard fetch API signature
   * Based on containers-starter-go implementation
   *
   * This method handles HTTP requests to the container. WebSocket requests done outside the DO*
   * won't work until https://github.com/cloudflare/workerd/issues/2319 is addressed. Until then, please use `switchPort` + `fetch()`.
   *
   * Method supports multiple signatures to match standard fetch API:
   * - containerFetch(request: Request, port?: number)
   * - containerFetch(url: string | URL, init?: RequestInit, port?: number)
   *
   * @param requestOrUrl The request object or URL string/object to send to the container
   * @param portOrInit Port number or fetch RequestInit options
   * @param portParam Optional port number when using URL+init signature
   * @returns A Response from the container, or WebSocket connection
   */
  async containerFetch(requestOrUrl, portOrInit, portParam) {
    let { request, port } = this.requestAndPortFromContainerFetchArgs(requestOrUrl, portOrInit, portParam);
    const state = await this.state.getState();
    if (!this.container.running || state.status !== "healthy") {
      try {
        await this.startAndWaitForPorts(port, { abort: request.signal });
      } catch (e) {
        if (isNoInstanceError(e)) {
          return new Response("There is no Container instance available at this time.\nThis is likely because you have reached your max concurrent instance count (set in wrangler config) or are you currently provisioning the Container.\nIf you are deploying your Container for the first time, check your dashboard to see provisioning status, this may take a few minutes.", { status: 503 });
        } else {
          return new Response(`Failed to start container: ${e instanceof Error ? e.message : String(e)}`, { status: 500 });
        }
      }
    }
    const tcpPort = this.container.getTcpPort(port);
    const containerUrl = request.url.replace("https:", "http:");
    try {
      this.renewActivityTimeout();
      const res = await tcpPort.fetch(containerUrl, request);
      return res;
    } catch (e) {
      if (!(e instanceof Error)) {
        throw e;
      }
      if (e.message.includes("Network connection lost.")) {
        return new Response("Container suddenly disconnected, try again", { status: 500 });
      }
      console.error(`Error proxying request to container ${this.ctx.id}:`, e);
      return new Response(`Error proxying request to container: ${e instanceof Error ? e.message : String(e)}`, { status: 500 });
    }
  }
  /**
   * Handle fetch requests to the Container
   * Default implementation forwards all HTTP and WebSocket requests to the container
   * Override this in your subclass to specify a port or implement custom request handling
   *
   * @param request The request to handle
   */
  async fetch(request) {
    const url = new URL(request.url);
    if (this.defaultPort === void 0 && url.port === "") {
      throw new Error("No port configured for this container. Set the defaultPort in your Container subclass, or set a port with switchPort.");
    }
    const portValue = +(url.port === "" ? this.defaultPort ?? "" : url.port);
    if (isNaN(portValue)) {
      throw new Error("port is not a number");
    }
    return await this.containerFetch(request, portValue);
  }
  // ===============================
  // ===============================
  //     PRIVATE METHODS & ATTRS
  // ===============================
  // ===============================
  // ==========================
  //     PRIVATE ATTRIBUTES
  // ==========================
  container;
  // onStopCalled will be true when we are in the middle of an onStop call
  onStopCalled = false;
  state;
  monitor;
  monitorSetup = false;
  sleepAfterMs = 0;
  // ==========================
  //     GENERAL HELPERS
  // ==========================
  /**
   * Execute SQL queries against the Container's database
   */
  sql(strings, ...values) {
    let query = "";
    query = strings.reduce((acc, str, i) => acc + str + (i < values.length ? "?" : ""), "");
    return [...this.ctx.storage.sql.exec(query, ...values)];
  }
  requestAndPortFromContainerFetchArgs(requestOrUrl, portOrInit, portParam) {
    let request;
    let port;
    if (requestOrUrl instanceof Request) {
      request = requestOrUrl;
      port = typeof portOrInit === "number" ? portOrInit : void 0;
    } else {
      const url = typeof requestOrUrl === "string" ? requestOrUrl : requestOrUrl.toString();
      const init = typeof portOrInit === "number" ? {} : portOrInit || {};
      port = typeof portOrInit === "number" ? portOrInit : typeof portParam === "number" ? portParam : void 0;
      request = new Request(url, init);
    }
    if (port === void 0 && this.defaultPort === void 0) {
      throw new Error("No port specified for container fetch. Set defaultPort or specify a port parameter.");
    }
    port = port ?? this.defaultPort;
    return { request, port };
  }
  // ===========================================
  //     CONTAINER INTERACTION & MONITORING
  // ===========================================
  // Tries to start a container if it's not running
  // Reutns the number of tries used
  async startContainerIfNotRunning(waitOptions, options) {
    if (this.container.running) {
      if (!this.monitor) {
        this.monitor = this.container.monitor();
      }
      return 0;
    }
    const abortedSignal = new Promise((res) => {
      waitOptions.abort?.addEventListener("abort", () => {
        res(true);
      });
    });
    await this.state.setRunning();
    for (let tries = 0; tries < waitOptions.retries; tries++) {
      const envVars = options?.envVars ?? this.envVars;
      const entrypoint = options?.entrypoint ?? this.entrypoint;
      const enableInternet = options?.enableInternet ?? this.enableInternet;
      const startConfig = {
        enableInternet
      };
      if (envVars && Object.keys(envVars).length > 0)
        startConfig.env = envVars;
      if (entrypoint)
        startConfig.entrypoint = entrypoint;
      this.renewActivityTimeout();
      const handleError = /* @__PURE__ */ __name(async () => {
        const err = await this.monitor?.catch((err2) => err2);
        if (typeof err === "number") {
          const toThrow = new Error(`Error starting container, early exit code 0 before we could check for healthiness, did it crash early?`);
          try {
            await this.onError(toThrow);
          } catch {
          }
          throw toThrow;
        } else if (!isNoInstanceError(err)) {
          try {
            await this.onError(err);
          } catch {
          }
          throw err;
        }
      }, "handleError");
      if (!this.container.running) {
        if (tries > 0) {
          await handleError();
        }
        await this.scheduleNextAlarm();
        this.container.start(startConfig);
        this.monitor = this.container.monitor();
      } else {
        await this.scheduleNextAlarm();
      }
      this.renewActivityTimeout();
      const port = this.container.getTcpPort(waitOptions.portToCheck);
      try {
        const combinedSignal = addTimeoutSignal(waitOptions.abort, PING_TIMEOUT_MS);
        await port.fetch("http://containerstarthealthcheck", { signal: combinedSignal });
        return tries;
      } catch (error) {
        if (isNotListeningError(error) && this.container.running) {
          return tries;
        }
        if (!this.container.running && isNotListeningError(error)) {
          await handleError();
        }
        console.warn("Error checking if container is ready:", error instanceof Error ? error.message : String(error));
        await Promise.any([
          new Promise((res) => setTimeout(res, waitOptions.waitInterval)),
          abortedSignal
        ]);
        if (waitOptions.abort?.aborted) {
          throw new Error("Aborted waiting for container to start as we received a cancellation signal");
        }
        if (TEMPORARY_HARDCODED_ATTEMPT_MAX === tries) {
          if (error instanceof Error && error.message.includes("Network connection lost")) {
            this.ctx.abort();
          }
          throw new Error(NO_CONTAINER_INSTANCE_ERROR);
        }
        continue;
      }
    }
    throw new Error(`Container did not start after ${waitOptions.retries} attempts`);
  }
  setupMonitorCallbacks() {
    if (this.monitorSetup) {
      return;
    }
    this.monitorSetup = true;
    this.monitor?.then(async () => {
      await this.ctx.blockConcurrencyWhile(async () => {
        await this.state.setStoppedWithCode(0);
      });
    }).catch(async (error) => {
      if (isNoInstanceError(error)) {
        return;
      }
      const exitCode = getExitCodeFromError(error);
      if (exitCode !== null) {
        await this.state.setStoppedWithCode(exitCode);
        this.monitorSetup = false;
        this.monitor = void 0;
        return;
      }
      try {
        await this.onError(error);
      } catch {
      }
    }).finally(() => {
      this.monitorSetup = false;
      if (this.timeout) {
        if (this.resolve)
          this.resolve();
        clearTimeout(this.timeout);
      }
    });
  }
  deleteSchedules(name) {
    this.sql`DELETE FROM container_schedules WHERE callback = ${name}`;
  }
  // ============================
  //     ALARMS AND SCHEDULES
  // ============================
  /**
   * Method called when an alarm fires
   * Executes any scheduled tasks that are due
   */
  async alarm(alarmProps) {
    if (alarmProps.isRetry && alarmProps.retryCount > MAX_ALARM_RETRIES) {
      const scheduleCount = Number(this.sql`SELECT COUNT(*) as count FROM container_schedules`[0]?.count) || 0;
      const hasScheduledTasks = scheduleCount > 0;
      if (hasScheduledTasks || this.container.running) {
        await this.scheduleNextAlarm();
      }
      return;
    }
    const prevAlarm = Date.now();
    await this.ctx.storage.setAlarm(prevAlarm);
    await this.ctx.storage.sync();
    const result = this.sql`
         SELECT * FROM container_schedules;
       `;
    let minTime = Date.now() + 3 * 60 * 1e3;
    const now = Date.now() / 1e3;
    for (const row of result) {
      if (row.time > now) {
        continue;
      }
      const callback = this[row.callback];
      if (!callback || typeof callback !== "function") {
        console.error(`Callback ${row.callback} not found or is not a function`);
        continue;
      }
      const schedule = this.getSchedule(row.id);
      try {
        const payload = row.payload ? JSON.parse(row.payload) : void 0;
        await callback.call(this, payload, await schedule);
      } catch (e) {
        console.error(`Error executing scheduled callback "${row.callback}":`, e);
      }
      this.sql`DELETE FROM container_schedules WHERE id = ${row.id}`;
    }
    const resultForMinTime = this.sql`
         SELECT * FROM container_schedules;
       `;
    const minTimeFromSchedules = Math.min(...resultForMinTime.map((r) => r.time * 1e3));
    if (!this.container.running) {
      await this.syncPendingStoppedEvents();
      if (resultForMinTime.length == 0) {
        await this.ctx.storage.deleteAlarm();
      } else {
        await this.ctx.storage.setAlarm(minTimeFromSchedules);
      }
      return;
    }
    if (this.isActivityExpired()) {
      await this.onActivityExpired();
      this.renewActivityTimeout();
      return;
    }
    minTime = Math.min(minTimeFromSchedules, minTime, this.sleepAfterMs);
    const timeout = Math.max(0, minTime - Date.now());
    await new Promise((resolve) => {
      this.resolve = resolve;
      if (!this.container.running) {
        resolve();
        return;
      }
      this.timeout = setTimeout(() => {
        resolve();
      }, timeout);
    });
    await this.ctx.storage.setAlarm(Date.now());
  }
  timeout;
  resolve;
  // synchronises container state with the container source of truth to process events
  async syncPendingStoppedEvents() {
    const state = await this.state.getState();
    if (!this.container.running && state.status === "healthy") {
      await this.callOnStop({ exitCode: 0, reason: "exit" });
      return;
    }
    if (!this.container.running && state.status === "stopped_with_code") {
      await this.callOnStop({ exitCode: state.exitCode ?? 0, reason: "exit" });
      return;
    }
  }
  async callOnStop(onStopParams) {
    if (this.onStopCalled) {
      return;
    }
    this.onStopCalled = true;
    const promise = this.onStop(onStopParams);
    if (promise instanceof Promise) {
      await promise.finally(() => {
        this.onStopCalled = false;
      });
    } else {
      this.onStopCalled = false;
    }
    await this.state.setStopped();
  }
  /**
   * Schedule the next alarm based on upcoming tasks
   */
  async scheduleNextAlarm(ms = 1e3) {
    const nextTime = ms + Date.now();
    if (this.timeout) {
      if (this.resolve)
        this.resolve();
      clearTimeout(this.timeout);
    }
    await this.ctx.storage.setAlarm(nextTime);
    await this.ctx.storage.sync();
  }
  async listSchedules(name) {
    const result = this.sql`
      SELECT * FROM container_schedules WHERE callback = ${name} LIMIT 1
    `;
    if (!result || result.length === 0) {
      return [];
    }
    return result.map(this.toSchedule);
  }
  toSchedule(schedule) {
    let payload;
    try {
      payload = JSON.parse(schedule.payload);
    } catch (e) {
      console.error(`Error parsing payload for schedule ${schedule.id}:`, e);
      payload = void 0;
    }
    if (schedule.type === "delayed") {
      return {
        taskId: schedule.id,
        callback: schedule.callback,
        payload,
        type: "delayed",
        time: schedule.time,
        delayInSeconds: schedule.delayInSeconds
      };
    }
    return {
      taskId: schedule.id,
      callback: schedule.callback,
      payload,
      type: "scheduled",
      time: schedule.time
    };
  }
  /**
   * Get a scheduled task by ID
   * @template T Type of the payload data
   * @param id ID of the scheduled task
   * @returns The Schedule object or undefined if not found
   */
  async getSchedule(id) {
    const result = this.sql`
      SELECT * FROM container_schedules WHERE id = ${id} LIMIT 1
    `;
    if (!result || result.length === 0) {
      return void 0;
    }
    const schedule = result[0];
    return this.toSchedule(schedule);
  }
  isActivityExpired() {
    return this.sleepAfterMs <= Date.now();
  }
};

// worker/index.js
var BidProofContainer = class extends Container {
  static {
    __name(this, "BidProofContainer");
  }
  defaultPort = 8080;
  requiredPorts = [8080];
  pingEndpoint = "/healthz";
  sleepAfter = "30m";
  enableInternet = true;
};
var index_default = {
  async fetch(request, env) {
    const container = env.BIDPROOF.getByName("singleton");
    await container.startAndWaitForPorts();
    return container.fetch(request);
  }
};
export {
  BidProofContainer,
  index_default as default
};
//# sourceMappingURL=index.js.map
