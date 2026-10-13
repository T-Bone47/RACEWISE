require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });

const { scrapeAll: scrapeDlpsgame } = require('../backend/scrapers/dlpsgameScraper');
const { scrapeAll: scrapeSuperpsx } = require('../backend/scrapers/superpsxScraper');
const Game = require('../backend/models/Game');
const { initializeDatabase } = require('../backend/config/database');

async function main() {
  console.log('Initializing database...');
  await initializeDatabase();

  console.log('Scraping dlpsgame.com...');
  const dlpsgameGames = await scrapeDlpsgame(3);
  console.log(`Found ${dlpsgameGames.length} games from dlpsgame`);

  console.log('Scraping superpsx.com...');
  const superpsxGames = await scrapeSuperpsx(3);
  console.log(`Found ${superpsxGames.length} games from superpsx`);

  const allGames = [...dlpsgameGames, ...superpsxGames];
  console.log(`Total games scraped: ${allGames.length}`);

  let created = 0;
  let updated = 0;
  let errors = 0;

  for (const game of allGames) {
    try {
      const existing = await Game.findById(game.title); // This would need a findByTitle method
      if (existing) {
        await Game.update(existing.id, game);
        updated++;
      } else {
        await Game.create(game);
        created++;
      }
    } catch (err) {
      console.error(`Error saving ${game.title}:`, err.message);
      errors++;
    }
  }

  console.log(`Done! Created: ${created}, Updated: ${updated}, Errors: ${errors}`);
  process.exit(0);
}

main().catch(err => {
  console.error('Scrape failed:', err);
  process.exit(1);
});