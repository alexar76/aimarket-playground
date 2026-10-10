import { run } from './client';

const args = process.argv.slice(2);
if (args.some(arg => arg !== '--invoke')) {
  console.error('Usage: node dist/cli.js [--invoke]');
  process.exitCode = 1;
} else {
  run({ invoke: args.includes('--invoke'), apiKey: process.env.AIMARKET_API_KEY })
    .then(result => console.log(JSON.stringify(result, null, 2)))
    .catch(error => {
      console.error(`Stopped (${error?.code === 'EEXIST' ? 'existing attempt' : 'request or verification failed'}). Inspect attempt.json / report.json; do not retry blindly.`);
      process.exitCode = 1;
    });
}
