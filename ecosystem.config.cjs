module.exports = {
  apps: [
    {
      name: 'backend',
      cwd: '/home/ubuntu/poc_ts',
      script: 'uv',
      args: 'run main.py --serve --host 0.0.0.0 --port 8001',
      interpreter: 'none',
      env: {
        PYTHONUNBUFFERED: '1'
      }
    },
    {
      name: 'frontend',
      cwd: '/home/ubuntu/poc_ts/frontend',
      script: 'npm',
      args: 'run dev -- --host 0.0.0.0 --port 3001',
      interpreter: 'none',
      env: {
        NODE_ENV: 'development'
      }
    }
  ]
};
