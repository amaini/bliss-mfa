/** @type {import('next').NextConfig} */
module.exports = {
  output: "standalone",
  // A stable build ID (the release commit) instead of a random one per build, so the
  // packaged portal is traceable to its source and repeat builds differ less.
  generateBuildId: async () => process.env.BLISS_BUILD_ID || "bliss-appliance-local",
};
