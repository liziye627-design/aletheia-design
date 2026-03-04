#!/usr/bin/env node

/**
 * API端点验证工具
 * 验证前端API客户端调用的所有端点在后端都有对应实现
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

// =====================================================
// 类型定义
// =====================================================

interface EndpointInfo {
  path: string;
  method: string;
  source: 'frontend' | 'backend';
  location?: string; // 文件位置
}

interface ComparisonResult {
  matched: EndpointInfo[];
  missingInBackend: EndpointInfo[];
  unusedInFrontend: EndpointInfo[];
}

function normalizePath(input: string): string {
  const raw = String(input || '').trim();
  if (!raw) return '/';
  const withoutTemplate = raw.replace(/\$\{[^}]+\}/g, '');
  const withoutQuery = withoutTemplate.split('?')[0] || '/';
  const withSlash = withoutQuery.startsWith('/') ? withoutQuery : `/${withoutQuery}`;
  const compact = withSlash.replace(/\/{2,}/g, '/');
  if (compact.length > 1 && compact.endsWith('/')) return compact.slice(0, -1);
  return compact;
}

// =====================================================
// 颜色输出
// =====================================================

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

function colorize(text: string, color: keyof typeof colors): string {
  return `${colors[color]}${text}${colors.reset}`;
}

// =====================================================
// 前端端点提取
// =====================================================

function extractFrontendEndpoints(apiClientPath: string): EndpointInfo[] {
  const endpoints: EndpointInfo[] = [];
  
  if (!fs.existsSync(apiClientPath)) {
    console.error(colorize(`❌ 前端API客户端文件不存在: ${apiClientPath}`, 'red'));
    return endpoints;
  }

  const content = fs.readFileSync(apiClientPath, 'utf-8');
  
  // 匹配 requestJson 调用中的路径和方法
  // 例如: requestJson<Type>('/path', { method: 'POST', ... })
  const requestJsonPattern = /requestJson<[^>]+>\(\s*['"`]([^'"`]+)['"`]\s*,\s*\{[^}]*method:\s*['"`](\w+)['"`]/g;
  
  let match;
  while ((match = requestJsonPattern.exec(content)) !== null) {
    const [, path, method] = match;
    endpoints.push({
      path: normalizePath(path),
      method: method.toUpperCase(),
      source: 'frontend',
      location: apiClientPath,
    });
  }

  // 匹配 fetch 调用
  const fetchPattern = /fetch\([^,]+['"`]([^'"`]+)['"`][^)]*\{[^}]*method:\s*['"`](\w+)['"`]/g;
  
  while ((match = fetchPattern.exec(content)) !== null) {
    const [, path, method] = match;
    if (!path.startsWith('http')) { // 排除完整URL
      endpoints.push({
        path: normalizePath(path),
        method: method.toUpperCase(),
        source: 'frontend',
        location: apiClientPath,
      });
    }
  }

  // 去重
  const uniqueEndpoints = Array.from(
    new Map(endpoints.map(e => [`${e.method}:${e.path}`, e])).values()
  );

  return uniqueEndpoints;
}

function extractRouterPrefixes(routerFilePath: string): Record<string, string> {
  const prefixes: Record<string, string> = {};
  if (!fs.existsSync(routerFilePath)) return prefixes;
  const content = fs.readFileSync(routerFilePath, 'utf-8');
  const includePattern =
    /include_router\(\s*([a-zA-Z_][\w]*)\.router[\s\S]*?prefix\s*=\s*['"`]([^'"`]+)['"`]/g;
  let match;
  while ((match = includePattern.exec(content)) !== null) {
    const [, moduleName, prefix] = match;
    prefixes[moduleName] = normalizePath(prefix);
  }
  return prefixes;
}

// =====================================================
// 后端端点提取
// =====================================================

function extractBackendEndpoints(backendApiDir: string): EndpointInfo[] {
  const endpoints: EndpointInfo[] = [];
  
  if (!fs.existsSync(backendApiDir)) {
    console.error(colorize(`❌ 后端API目录不存在: ${backendApiDir}`, 'red'));
    return endpoints;
  }

  // 递归读取所有Python文件
  function readPythonFiles(dir: string): string[] {
    const files: string[] = [];
    const items = fs.readdirSync(dir);
    
    for (const item of items) {
      const fullPath = path.join(dir, item);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory() && !item.startsWith('__')) {
        files.push(...readPythonFiles(fullPath));
      } else if (stat.isFile() && item.endsWith('.py')) {
        files.push(fullPath);
      }
    }
    
    return files;
  }

  const pythonFiles = readPythonFiles(backendApiDir);
  const routerFilePath = path.join(backendApiDir, 'v1', 'router.py');
  const routerPrefixes = extractRouterPrefixes(routerFilePath);

  for (const file of pythonFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const moduleName = path.basename(file, '.py');
    const modulePrefix = routerPrefixes[moduleName] || '';
    
    // 匹配 FastAPI 路由装饰器
    // @router.get("/path")
    // @router.post("/path")
    const routerPattern = /@router\.(get|post|put|delete|patch|options)\s*\(\s*['"`]([^'"`]+)['"`]/g;
    
    let match;
    while ((match = routerPattern.exec(content)) !== null) {
      const [, method, routePath] = match;
      const fullPath = normalizePath(`${modulePrefix || ''}/${routePath || ''}`);
      endpoints.push({
        path: fullPath,
        method: method.toUpperCase(),
        source: 'backend',
        location: file,
      });
    }
  }

  return endpoints;
}

// =====================================================
// 端点比对
// =====================================================

function compareEndpoints(
  frontendEndpoints: EndpointInfo[],
  backendEndpoints: EndpointInfo[]
): ComparisonResult {
  const matched: EndpointInfo[] = [];
  const missingInBackend: EndpointInfo[] = [];
  const unusedInFrontend: EndpointInfo[] = [];

  // 创建后端端点映射
  const backendMap = new Map<string, EndpointInfo>();
  for (const endpoint of backendEndpoints) {
    const key = `${endpoint.method}:${endpoint.path}`;
    backendMap.set(key, endpoint);
  }

  // 创建前端端点映射
  const frontendMap = new Map<string, EndpointInfo>();
  for (const endpoint of frontendEndpoints) {
    const key = `${endpoint.method}:${endpoint.path}`;
    frontendMap.set(key, endpoint);
  }

  // 检查前端端点是否在后端存在
  for (const frontendEndpoint of frontendEndpoints) {
    const key = `${frontendEndpoint.method}:${frontendEndpoint.path}`;
    
    if (backendMap.has(key)) {
      matched.push(frontendEndpoint);
    } else {
      missingInBackend.push(frontendEndpoint);
    }
  }

  // 检查后端端点是否被前端使用
  for (const backendEndpoint of backendEndpoints) {
    const key = `${backendEndpoint.method}:${backendEndpoint.path}`;
    
    if (!frontendMap.has(key)) {
      unusedInFrontend.push(backendEndpoint);
    }
  }

  return { matched, missingInBackend, unusedInFrontend };
}

// =====================================================
// 生成报告
// =====================================================

function generateReport(result: ComparisonResult): void {
  console.log('\n' + colorize('========================================', 'blue'));
  console.log(colorize('  API端点验证报告', 'blue'));
  console.log(colorize('========================================', 'blue') + '\n');

  // 匹配的端点
  console.log(colorize(`✅ 匹配的端点: ${result.matched.length}`, 'green'));
  if (result.matched.length > 0) {
    for (const endpoint of result.matched) {
      console.log(`   ${endpoint.method.padEnd(7)} ${endpoint.path}`);
    }
  }
  console.log('');

  // 后端缺失的端点
  if (result.missingInBackend.length > 0) {
    console.log(colorize(`❌ 后端缺失的端点: ${result.missingInBackend.length}`, 'red'));
    for (const endpoint of result.missingInBackend) {
      console.log(`   ${endpoint.method.padEnd(7)} ${endpoint.path}`);
      console.log(colorize(`      位置: ${endpoint.location}`, 'yellow'));
    }
    console.log('');
  }

  // 前端未使用的端点
  if (result.unusedInFrontend.length > 0) {
    console.log(colorize(`⚠️  前端未使用的端点: ${result.unusedInFrontend.length}`, 'yellow'));
    for (const endpoint of result.unusedInFrontend) {
      console.log(`   ${endpoint.method.padEnd(7)} ${endpoint.path}`);
    }
    console.log('');
  }

  // 总结
  console.log(colorize('========================================', 'blue'));
  if (result.missingInBackend.length === 0) {
    console.log(colorize('✅ 所有前端端点都有后端实现！', 'green'));
  } else {
    console.log(colorize(`❌ 发现 ${result.missingInBackend.length} 个端点缺失`, 'red'));
  }
  console.log(colorize('========================================', 'blue') + '\n');
}

// =====================================================
// 主函数
// =====================================================

function main(): void {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const projectRoot = path.resolve(__dirname, '..');
  const frontendApiClient = path.join(projectRoot, 'frontend', 'src', 'api.ts');
  const backendApiDir = path.join(projectRoot, 'aletheia-backend', 'api');

  console.log(colorize('🔍 开始验证API端点...', 'cyan'));
  console.log(`   前端API客户端: ${frontendApiClient}`);
  console.log(`   后端API目录: ${backendApiDir}\n`);

  // 提取端点
  const frontendEndpoints = extractFrontendEndpoints(frontendApiClient);
  const backendEndpoints = extractBackendEndpoints(backendApiDir);

  console.log(colorize(`📊 提取结果:`, 'cyan'));
  console.log(`   前端端点: ${frontendEndpoints.length}`);
  console.log(`   后端端点: ${backendEndpoints.length}\n`);

  // 比对端点
  const result = compareEndpoints(frontendEndpoints, backendEndpoints);

  // 生成报告
  generateReport(result);

  // 退出码
  process.exit(result.missingInBackend.length > 0 ? 1 : 0);
}

// 运行
const isMain = (() => {
  const thisFile = fileURLToPath(import.meta.url);
  const entry = process.argv[1] ? path.resolve(process.argv[1]) : '';
  return Boolean(entry) && thisFile === entry;
})();

if (isMain) {
  main();
}

export { extractFrontendEndpoints, extractBackendEndpoints, compareEndpoints };
