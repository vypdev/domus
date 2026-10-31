import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import '../src/probe-toggle';
const meta: Meta = {title: 'Probe/Toggle', render: () => html`<probe-toggle></probe-toggle>`};
export default meta;
export const Default: StoryObj = {};
