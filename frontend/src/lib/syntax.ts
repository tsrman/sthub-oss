export function getLanguageFromPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'py':
      return 'python';
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'json':
      return 'json';
    case 'yaml':
    case 'yml':
      return 'yaml';
    case 'md':
      return 'markdown';
    case 'html':
      return 'html';
    case 'css':
      return 'css';
    default:
      return 'plaintext';
  }
}

export function isTextFile(contentType: string): boolean {
  return contentType.startsWith('text/') || contentType === 'application/json';
}

export function isImageFile(contentType: string): boolean {
  return contentType.startsWith('image/');
}

const TEXT_EXTENSIONS = new Set([
  'py',
  'txt',
  'md',
  'json',
  'yaml',
  'yml',
  'toml',
  'env',
  'csv',
  'log',
  'cfg',
  'ini',
  'css',
  'html',
  'js',
  'jsx',
  'ts',
  'tsx',
]);

export function isTextPath(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase();
  return ext ? TEXT_EXTENSIONS.has(ext) : false;
}
