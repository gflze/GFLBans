export default [
    {
        files: ['**/*.js'],
        ignores: ['static/3rdparty/**'],
        rules: {
            'no-unexpected-multiline': 'error',
            'quotes': ['error', 'single'],
            'indent': ['error', 4],
            'brace-style': ['error', '1tbs'],
            'semi': ['error', 'always'],
            'max-len': ['error', { 'code': 120, 'ignoreUrls': true }],
            'spaced-comment': ['error', 'always']
        }
    }
];
