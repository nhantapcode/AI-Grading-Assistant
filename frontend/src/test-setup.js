import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(cleanup);
HTMLDialogElement.prototype.showModal = function () { this.open = true; };
