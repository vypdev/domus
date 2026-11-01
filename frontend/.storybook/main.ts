import type {StorybookConfig} from '@storybook/web-components-vite';

const configuration: StorybookConfig = {
  stories: ['../stories/**/*.stories.ts'],
  framework: '@storybook/web-components-vite',
  addons: [],
  core: {disableTelemetry: true},
};
export default configuration;
