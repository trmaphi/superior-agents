module.exports = {
    "apps": [{
      "name": "superior-agent-server",
      "script": "server.ts",
      "instances": "max",
      "exec_mode": "cluster",
      "interpreter": "node",
      "interpreter_args": "-r ts-node/register",
      "watch": true,
      "ignore_watch": ["node_modules", "logs", "dist"],
      "max_memory_restart": "4G",
      "env": {
        "NODE_ENV": "production",
        "TS_NODE_PROJECT": "./tsconfig.json"
      },
      "error_file": "logs/err.log",
      "out_file": "logs/out.log",
      "log_date_format": "YYYY-MM-DD HH:mm:ss",
      "merge_logs": true,
      "autorestart": true,
      "restart_delay": 4000,
      "max_restarts": 10,
      "wait_ready": true,
      "listen_timeout": 8000,
      "kill_timeout": 1600,
      "source_map_support": true
    }]
  }