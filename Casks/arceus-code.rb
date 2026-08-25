cask "arceus-code" do
  version "1.0.0"
  sha256 "REPLACE_WITH_RELEASE_SHA256"

  url "https://github.com/amarreddy1432723-lang/autonomus_ai/releases/download/arceus-code-v#{version}/Arceus-Code-#{version}.dmg",
      verified: "github.com/amarreddy1432723-lang/autonomus_ai/"
  name "Arceus Code"
  desc "Desktop-first AI coding workspace"
  homepage "https://github.com/amarreddy1432723-lang/autonomus_ai"

  app "Arceus Code.app"

  zap trash: [
    "~/Library/Application Support/Arceus Code",
    "~/Library/Preferences/dev.arceus.code.plist",
    "~/Library/Saved Application State/dev.arceus.code.savedState",
  ]
end
