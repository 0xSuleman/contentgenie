/* eslint-disable @typescript-eslint/no-var-requires */
const darkCodeTheme = require('prism-react-renderer/themes/dracula');
const lightCodeTheme = require('prism-react-renderer/themes/github');

/** @type {import('@docusaurus/types').DocusaurusConfig} */
(
  module.exports = {
    title: 'ContentGenie',
    tagline: 'AI content automation for YouTube Shorts',
    url: 'https://localhost',
    baseUrl: '/',
    favicon: 'img/contentgenie-favicon.svg',
    organizationName: 'Local',
    projectName: 'ContentGenie',
    onBrokenLinks: 'throw',
    onBrokenMarkdownLinks: 'throw',
    presets: [
      [
        '@docusaurus/preset-classic',
        /** @type {import('@docusaurus/preset-classic').Options} */
        ({
          docs: {
            path: 'docs',
            sidebarPath: 'sidebars.js',
            versions: {
              current: {
                label: 'current',
              },
            },
            lastVersion: 'current',
            showLastUpdateAuthor: true,
            showLastUpdateTime: true,
          },
          theme: {
            customCss: require.resolve('./src/css/custom.css'),
          },
        }),
      ],
    ],
    plugins: ['tailwind-loader'],
    themeConfig:
      /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
      ({
        navbar: {
          hideOnScroll: true,
          logo: {
            alt: 'ContentGenie',
            src: 'img/contentgenie-mark.svg',
          },
          items: [
            {
              label: 'Docs',
              to: 'docs/how-to-install',
              position: 'right',
            },
            {
              type: 'docsVersionDropdown',
              position: 'right',
            },
          ],
        },
        colorMode: {
          defaultMode: 'light',
          disableSwitch: false,
          respectPrefersColorScheme: true,
        },
        footer: {
          links: [
            {
              title: 'Docs',
              items: [
                {
                  label: 'Getting Started',
                  to: 'docs/how-to-install',
                },
              ],
            },
          ],
          copyright: `ContentGenie ${new Date().getFullYear()}`,
        },
        prism: {
          theme: lightCodeTheme,
          darkTheme: darkCodeTheme,
        },
      }),
  }
);
