# Fuse.gg Website - TypeScript Version

This is the TypeScript implementation of the Fuse.gg gaming bypass website.

## Project Structure

```
web/
├── src/
│   ├── types.ts         # TypeScript type definitions
│   ├── main.ts          # Main application entry point
│   ├── cart.ts          # Shopping cart system
│   ├── checkout.ts      # Checkout process
│   ├── payments.ts      # Payment processing (PayPal & Crypto)
│   ├── particles.ts     # Particle animation system
│   ├── navigation.ts    # Navigation/tab system
│   └── utils.ts         # Utility functions
├── dist/                # Compiled JavaScript output
├── index.html           # Main HTML file
├── tsconfig.json        # TypeScript configuration
└── package.json         # NPM dependencies

## Setup

1. Install dependencies:
```bash
npm install
```

2. Build the TypeScript code:
```bash
npm run build
```

3. For development with auto-rebuild:
```bash
npm run dev
```

## Building

The TypeScript files in `src/` are compiled to JavaScript in the `dist/` directory.

To build:
```bash
npm run build
```

To clean build artifacts:
```bash
npm run clean
```

## Usage

After building, update your `index.html` to include the compiled JavaScript:

```html
<script type="module" src="dist/main.js"></script>
```

## Features

- **Modular TypeScript Architecture**: Clean separation of concerns
- **Type Safety**: Full TypeScript type checking
- **Shopping Cart**: Add/remove products, view cart
- **Checkout System**: Email validation, coupon codes, payment method selection
- **Payment Processing**: PayPal and cryptocurrency support (Bitcoin, Litecoin, Solana)
- **Particle Animation**: Constellation-style animated background
- **Navigation**: Tab-based navigation system
- **Responsive Design**: Mobile-friendly layout

## Development

The codebase is organized into modules:

- `types.ts`: All TypeScript interfaces and types
- `main.ts`: Application initialization and global setup
- `cart.ts`: Shopping cart functionality
- `checkout.ts`: Checkout form and validation
- `payments.ts`: Payment processing logic
- `particles.ts`: Background particle animation
- `navigation.ts`: Tab navigation system
- `utils.ts`: Shared utility functions

## Deployment

See `DEPLOYMENT.md` for deployment instructions to production.
