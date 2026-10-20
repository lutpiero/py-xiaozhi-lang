# py-xiaozhi Documentation

This is the documentation site for the py-xiaozhi project, built with VitePress.

## Features

- Project guides: detailed usage and development documentation
- Sponsors page: showcases and thanks all project sponsors
- Contributing guide: explains how to contribute code
- Contributors list: showcases all developers who contributed to the project
- Responsive design: adapts to desktop and mobile devices

## Local Development

```bash
# Install dependencies
pnpm install

# Start the development server
pnpm docs:dev

# Build static files
pnpm docs:build

# Preview the build output
pnpm docs:preview
```

## Directory Structure

```
documents/
├── docs/                  # documentation sources
│   ├── .vitepress/        # VitePress configuration
│   ├── guide/             # guides
│   ├── sponsors/          # sponsors page
│   ├── contributing.md    # contributing guide
│   ├── contributors.md    # contributors list
│   └── index.md           # home page
├── package.json           # project configuration
└── README.md              # project readme
```

## Sponsors Page

The sponsors page works as follows:

1. The `/sponsors/` directory contains sponsor-related content
2. `data.json` stores sponsor data
3. A Vue component renders the sponsor list dynamically on the client
4. Detailed instructions and payment methods for becoming a sponsor are provided

## Contributing Guide

The contributing guide page covers:

1. Development environment setup
2. Code contribution workflow
3. Coding and commit conventions
4. Pull request creation and review workflow
5. Documentation contribution guidelines

## Contributors List

The contributors page showcases everyone who contributed to the project, including:

1. Core development team members
2. Code contributors
3. Documentation contributors
4. Testers and feedback providers

## Deployment

The documentation site is automatically deployed to GitHub Pages through GitHub Actions.
