#!/usr/bin/env node

const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const net = require("net");

const args = process.argv.slice(2);
const command = args[0];

function printHelp() {
  console.log(`
Arceus OS CLI - Command Line Developer Interface
Usage:
  Arceus start                  Start the standalone Arceus OS desktop shell and services
  Arceus stop                   Terminate all running Arceus OS background services
  Arceus status                 Check the status of running microservices and ports
  Arceus open <folder_path>     Import and open a local project folder directly in Arceus
  Arceus --help                 Show this help menu
`);
}

async function checkPortStatus(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(500);
    socket.on("connect", () => {
      socket.destroy();
      resolve(true); // Occupied
    });
    socket.on("timeout", () => {
      socket.destroy();
      resolve(false); // Free
    });
    socket.on("error", () => {
      socket.destroy();
      resolve(false); // Free
    });
    socket.connect(port, "127.0.0.1");
  });
}

async function getStatus() {
  const ports = {
    "Next.js Frontend": 3000,
    "Auth Microservice": 8001,
    "Goals Microservice": 8002,
    "Agent Microservice": 8003
  };
  
  console.log("Arceus OS Microservices Status:");
  for (const [name, port] of Object.entries(ports)) {
    const active = await checkPortStatus(port);
    console.log(`  - ${name} (Port ${port}): ${active ? "\x1b[32mRUNNING\x1b[0m" : "\x1b[31mOFFLINE\x1b[0m"}`);
  }
}

function stopServices() {
  console.log("Stopping all running Arceus OS microservices...");
  try {
    if (process.platform === "win32") {
      execSync("taskkill /IM uvicorn.exe /F", { stdio: "ignore" });
      execSync("taskkill /IM node.exe /F /FI \"WINDOWTITLE eq Next.js*\"", { stdio: "ignore" });
      console.log("\x1b[32mSuccessfully terminated local processes.\x1b[0m");
    } else {
      execSync("pkill -f uvicorn", { stdio: "ignore" });
      execSync("pkill -f 'next-server'", { stdio: "ignore" });
      console.log("\x1b[32mSuccessfully terminated local processes.\x1b[0m");
    }
  } catch (e) {
    console.log("No active background service processes were found.");
  }
}

function startServices(openPath = "") {
  const exeDir = path.join(__dirname, "dist", "Arceus OS-win32-x64");
  const exePath = path.join(exeDir, "Arceus OS.exe");
  
  if (!fs.existsSync(exePath)) {
    // Fallback to dev start
    console.log("Launcher executable not found in dist. Starting in Dev mode...");
    const devArgs = openPath ? [".", openPath] : ["."];
    const devProcess = spawn("npx", ["electron", ...devArgs], {
      cwd: __dirname,
      detached: true,
      stdio: "ignore",
      shell: true
    });
    devProcess.unref();
    console.log("\x1b[32mArceus Dev Shell spawned successfully.\x1b[0m");
    return;
  }
  
  console.log(`Launching Arceus OS: ${exePath}`);
  const spawnArgs = openPath ? [openPath] : [];
  const p = spawn(exePath, spawnArgs, {
    detached: true,
    stdio: "ignore"
  });
  p.unref();
  console.log("\x1b[32mArceus OS launched successfully.\x1b[0m");
}

async function handleCommand() {
  switch (command) {
    case "start":
      startServices();
      break;
    case "stop":
      stopServices();
      break;
    case "status":
      await getStatus();
      break;
    case "open":
      const targetPath = args[1];
      if (!targetPath) {
        console.error("\x1b[31mError: Please specify a folder path to open.\x1b[0m");
        process.exit(1);
      }
      const absPath = path.resolve(targetPath);
      if (!fs.existsSync(absPath) || !fs.statSync(absPath).isDirectory()) {
        console.error(`\x1b[31mError: Path "${absPath}" is not a valid directory.\x1b[0m`);
        process.exit(1);
      }
      startServices(absPath);
      break;
    case "--help":
    case "-h":
    default:
      printHelp();
      break;
  }
}

handleCommand();
