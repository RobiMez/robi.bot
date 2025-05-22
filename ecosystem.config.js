module.exports = {
  apps: [{
    name: "telegram-bot",
    script: "main.py",
    interpreter: "./venv/bin/python",
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: "200M",
    env: {
      NODE_ENV: "production"
    }
  }]
};
