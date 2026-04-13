import('motion/react').then(() => console.log('Found')).catch((e) => {
  console.log('Not Found');
  console.error(e);
});
