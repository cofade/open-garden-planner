# Plant API Setup Guide

Open Garden Planner integrates with online plant databases to help you search for plant species and automatically populate botanical information. This guide explains how to obtain and configure API keys for the supported plant databases.

## Supported Plant APIs

The application supports multiple plant APIs with automatic fallback:

1. **Trefle.io** (Primary) - Comprehensive botanical database, 400,000+ species
2. **Perenual** (Secondary) - Most reliable, 10,000+ species
3. **Permapeople** (Tertiary) - Community-driven, permaculture-focused
4. Bundled Database (Future) - Offline fallback

## Setup Instructions

### Option 1: Trefle.io API (Recommended)

Trefle.io offers a free tier with access to 400,000+ plant species with comprehensive botanical information including growth requirements, distribution, images, and more.

**Steps:**
1. Visit [https://trefle.io/](https://trefle.io/)
2. Sign up for a free account
3. Navigate to your profile to get your API token
4. Set the environment variable or add to `.env` file:
   ```bash
   # Windows (Command Prompt)
   set TREFLE_API_TOKEN=your_token_here

   # Windows (PowerShell)
   $env:TREFLE_API_TOKEN="your_token_here"

   # Linux/Mac
   export TREFLE_API_TOKEN=your_token_here

   # Or add to .env file in project root:
   TREFLE_API_TOKEN=your_token_here
   ```

**Features:**
- 400,000+ plant species
- Comprehensive botanical data
- Growth requirements (light, pH, humidity)
- Distribution and native range information
- Multiple images per plant (flower, leaf, habit, fruit, bark)
- Edible parts and toxicity information
- Scientific taxonomy and synonyms

### Option 2: Perenual API

Perenual offers a free tier with 10,000 API requests per day and access to 10,000+ plant species.

**Steps:**
1. Visit [https://perenual.com/](https://perenual.com/)
2. Sign up for a free account
3. Navigate to your API dashboard
4. Copy your API key
5. Set the environment variable:
   ```bash
   # Windows (Command Prompt)
   set PERENUAL_API_KEY=your_key_here

   # Windows (PowerShell)
   $env:PERENUAL_API_KEY="your_key_here"

   # Linux/Mac
   export PERENUAL_API_KEY=your_key_here
   ```

**Features:**
- 10,000 requests/day (free tier)
- Plant images included
- Growth requirements (sun, water, hardiness zones)
- Well-maintained and reliable

### Option 3: Permapeople API

Permapeople is a community-driven plant database focused on permaculture and edible plants. It's free for non-commercial use and licensed under CC BY-SA 4.0.

**Steps:**
1. Visit [https://permapeople.org/api_requests/new](https://permapeople.org/api_requests/new)
2. Sign up for an account
3. Request API access
4. You'll receive a key ID and key secret
5. Set the environment variables:
   ```bash
   # Windows (Command Prompt)
   set PERMAPEOPLE_KEY_ID=your_key_id_here
   set PERMAPEOPLE_KEY_SECRET=your_key_secret_here

   # Windows (PowerShell)
   $env:PERMAPEOPLE_KEY_ID="your_key_id_here"
   $env:PERMAPEOPLE_KEY_SECRET="your_key_secret_here"

   # Linux/Mac
   export PERMAPEOPLE_KEY_ID=your_key_id_here
   export PERMAPEOPLE_KEY_SECRET=your_key_secret_here
   ```

**Features:**
- Free for non-commercial use
- Edible and medicinal plant focus
- Permaculture-specific information
- Community-contributed data

## Usage in the Application

Once you've configured API keys, the plant search feature will automatically:

1. Try each API in order (Trefle → Perenual → Permapeople → ...)
2. Use the first one that successfully returns results
3. Display plant information including:
   - Common and scientific names
   - Sun and water requirements
   - Hardiness zones
   - Growth characteristics
   - Edible parts (if applicable)
   - Images (when available)

## Troubleshooting

### "API key not configured" Error

Make sure you've set the environment variables correctly and restarted the application after setting them.

### No Results Found

- Check your internet connection
- Verify your API keys are correct
- Try a different plant name or spelling
- Some APIs may have rate limits - wait a few minutes and try again

### All APIs Failed

If all APIs fail:
1. Check your internet connection
2. Verify API keys are still valid
3. Check the API status pages:
   - Trefle: [https://trefle.io/](https://trefle.io/)
   - Perenual: [https://perenual.com/](https://perenual.com/)
   - Permapeople: [https://permapeople.org/](https://permapeople.org/)

## API Credits and Attribution

When using these APIs, please:

- **Trefle.io**: Free for personal and commercial use with attribution
- **Perenual**: Free for personal and commercial use
- **Permapeople**: Provide attribution and link back to permapeople.org. Data is CC BY-SA 4.0 licensed.

## Future Enhancements

Planned features for future releases:
- Bundled offline plant database
- Custom plant library (user-defined entries)
- Plant data caching for offline use
- Advanced filtering (by zone, edibility, growth characteristics)
