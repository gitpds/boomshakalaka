module.exports = {
  testEnvironment: 'jsdom',
  testMatch: ['**/tests/unit/**/*.test.js'],
  setupFilesAfterEnv: ['<rootDir>/tests/setup.js'],
  moduleFileExtensions: ['js'],
  verbose: true
};
