module.exports = {
  apps: [
    {
      name: "backend",
      script: "./scripts/pm2-backend.sh",
      interpreter: "bash",
      cwd: ".",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "frontend",
      script: "./scripts/pm2-frontend.sh",
      interpreter: "bash",
      cwd: ".",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        NODE_ENV: "development",
      },
    },
    {
      name: "detector-in",
      script: "./scripts/pm2-detector-in.sh",
      interpreter: "bash",
      cwd: ".",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "detector-out",
      script: "./scripts/pm2-detector-out.sh",
      interpreter: "bash",
      cwd: ".",
      watch: false,
      autorestart: false,
    },
  ],
};
