#!/usr/bin/env node

/**
 * API连通性测试套件
 * 测试关键API端点的连通性和响应格式
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

// =====================================================
// 类型定义
// =====================================================

interface TestCase {
  name: string;
  endpoint: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'OPTIONS';
  payload?: any;
  expectedStatus: number;
  validateResponse: (response: any) => boolean;
  validationMessage?: string;
}

interface TestResult {
  testCase: TestCase;
  passed: boolean;
  error?: string;
  responseTime?: number;
  statusCode?: number;
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
// 配置
// =====================================================

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';
const API_V1 = `${API_BASE}/api/v1`;

// =====================================================
// 测试用例定义
// =====================================================

const testCases: TestCase[] = [
  // 1. 健康检查
  {
    name: '健康检查',
    endpoint: `${API_BASE}/health`,
    method: 'GET',
    expectedStatus: 200,
    validateResponse: (res) => res.status === 'healthy',
    validationMessage: '响应应包含 status: "healthy"',
  },

  // 2. 增强分析API
  {
    name: '增强分析API',
    endpoint: `${API_V1}/intel/enhanced/analyze/enhanced`,
    method: 'POST',
    payload: {
      content: '测试内容：这是一条用于测试的信息',
      source_platform: 'web',
    },
    expectedStatus: 200,
    validateResponse: (res) => 
      res.intel && 
      res.reasoning_chain && 
      typeof res.processing_time_ms === 'number',
    validationMessage: '响应应包含 intel, reasoning_chain, processing_time_ms',
  },

  // 3. 历史记录搜索API
  {
    name: '历史记录搜索API',
    endpoint: `${API_V1}/intel/enhanced/search`,
    method: 'POST',
    payload: {
      keyword: '',
      page: 1,
      page_size: 10,
    },
    expectedStatus: 200,
    validateResponse: (res) => 
      Array.isArray(res.items) &&
      typeof res.total === 'number' &&
      typeof res.page === 'number' &&
      typeof res.page_size === 'number' &&
      typeof res.has_more === 'boolean',
    validationMessage: '响应应包含 items[], total, page, page_size, has_more',
  },

  // 4. 多平台搜索API
  {
    name: '多平台搜索API',
    endpoint: `${API_V1}/multiplatform/search`,
    method: 'POST',
    payload: {
      keyword: '测试',
      platforms: ['weibo'],
      limit_per_platform: 5,
    },
    expectedStatus: 200,
    validateResponse: (res) => res !== null && typeof res === 'object',
    validationMessage: '响应应为对象',
  },

  // 5. Playwright编排API
  {
    name: 'Playwright编排API',
    endpoint: `${API_V1}/multiplatform/playwright-orchestrate`,
    method: 'POST',
    payload: {
      keywords: ['测试'],
      platforms: ['bilibili'],
      limit_per_platform: 5,
      max_concurrent_agents: 1,
      headless: true,
    },
    expectedStatus: 200,
    validateResponse: (res) => 
      Array.isArray(res.keywords) &&
      typeof res.data === 'object',
    validationMessage: '响应应包含 keywords[], data{}',
  },
];

// =====================================================
// 测试执行引擎
// =====================================================

async function runTest(testCase: TestCase): Promise<TestResult> {
  const startTime = Date.now();
  
  try {
    const options: RequestInit = {
      method: testCase.method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (testCase.payload) {
      options.body = JSON.stringify(testCase.payload);
    }

    const response = await fetch(testCase.endpoint, options);
    const responseTime = Date.now() - startTime;
    const statusCode = response.status;

    // 检查状态码
    if (statusCode !== testCase.expectedStatus) {
      return {
        testCase,
        passed: false,
        error: `状态码不匹配: 期望 ${testCase.expectedStatus}, 实际 ${statusCode}`,
        responseTime,
        statusCode,
      };
    }

    // 解析响应
    let responseData;
    try {
      responseData = await response.json();
    } catch (e) {
      return {
        testCase,
        passed: false,
        error: '无法解析JSON响应',
        responseTime,
        statusCode,
      };
    }

    // 验证响应格式
    const isValid = testCase.validateResponse(responseData);
    
    if (!isValid) {
      return {
        testCase,
        passed: false,
        error: `响应格式验证失败: ${testCase.validationMessage || '未知错误'}`,
        responseTime,
        statusCode,
      };
    }

    return {
      testCase,
      passed: true,
      responseTime,
      statusCode,
    };

  } catch (error) {
    const responseTime = Date.now() - startTime;
    return {
      testCase,
      passed: false,
      error: error instanceof Error ? error.message : '未知错误',
      responseTime,
    };
  }
}

// =====================================================
// 生成测试报告
// =====================================================

function generateReport(results: TestResult[]): void {
  console.log('\n' + colorize('========================================', 'blue'));
  console.log(colorize('  API连通性测试报告', 'blue'));
  console.log(colorize('========================================', 'blue') + '\n');

  let passedCount = 0;
  let failedCount = 0;

  for (const result of results) {
    if (result.passed) {
      passedCount++;
      console.log(colorize(`✅ ${result.testCase.name}`, 'green'));
      console.log(`   端点: ${result.testCase.method} ${result.testCase.endpoint}`);
      console.log(`   状态码: ${result.statusCode}`);
      console.log(`   响应时间: ${result.responseTime}ms\n`);
    } else {
      failedCount++;
      console.log(colorize(`❌ ${result.testCase.name}`, 'red'));
      console.log(`   端点: ${result.testCase.method} ${result.testCase.endpoint}`);
      if (result.statusCode) {
        console.log(`   状态码: ${result.statusCode}`);
      }
      if (result.responseTime) {
        console.log(`   响应时间: ${result.responseTime}ms`);
      }
      console.log(colorize(`   错误: ${result.error}`, 'red'));
      
      // 调试建议
      if (result.error?.includes('fetch failed') || result.error?.includes('ECONNREFUSED')) {
        console.log(colorize('   💡 建议: 请确认后端服务已启动 (http://localhost:8000)', 'yellow'));
      } else if (result.statusCode === 404) {
        console.log(colorize('   💡 建议: 端点不存在，请检查API路由配置', 'yellow'));
      } else if (result.statusCode === 422) {
        console.log(colorize('   💡 建议: 请求参数格式错误，请检查payload', 'yellow'));
      } else if (result.statusCode && result.statusCode >= 500) {
        console.log(colorize('   💡 建议: 服务器内部错误，请查看后端日志', 'yellow'));
      }
      console.log('');
    }
  }

  // 总结
  console.log(colorize('========================================', 'blue'));
  console.log(`总计: ${results.length} 个测试`);
  console.log(colorize(`通过: ${passedCount}`, 'green'));
  if (failedCount > 0) {
    console.log(colorize(`失败: ${failedCount}`, 'red'));
  }
  console.log(colorize('========================================', 'blue') + '\n');

  if (failedCount === 0) {
    console.log(colorize('🎉 所有测试通过！', 'green') + '\n');
  } else {
    console.log(colorize('⚠️  部分测试失败，请查看上述错误信息', 'yellow') + '\n');
  }
}

// =====================================================
// 主函数
// =====================================================

async function main(): Promise<void> {
  console.log(colorize('🔍 开始API连通性测试...', 'cyan'));
  console.log(`   API基础地址: ${API_BASE}`);
  console.log(`   测试用例数: ${testCases.length}\n`);

  // 首先测试后端是否可访问
  console.log(colorize('📡 检查后端连接...', 'cyan'));
  try {
    const response = await fetch(`${API_BASE}/health`, { method: 'GET' });
    if (response.ok) {
      console.log(colorize('✅ 后端服务可访问\n', 'green'));
    } else {
      console.log(colorize(`⚠️  后端响应异常 (状态码: ${response.status})\n`, 'yellow'));
    }
  } catch (error) {
    console.log(colorize('❌ 无法连接到后端服务', 'red'));
    console.log(colorize(`   错误: ${error instanceof Error ? error.message : '未知错误'}`, 'red'));
    console.log(colorize('   💡 请确认后端已启动: http://localhost:8000\n', 'yellow'));
    process.exit(1);
  }

  // 运行所有测试
  console.log(colorize('🧪 运行测试用例...\n', 'cyan'));
  const results: TestResult[] = [];

  for (const testCase of testCases) {
    const result = await runTest(testCase);
    results.push(result);
  }

  // 生成报告
  generateReport(results);

  // 退出码
  const failedCount = results.filter(r => !r.passed).length;
  process.exit(failedCount > 0 ? 1 : 0);
}

// 运行
const isMain = (() => {
  const thisFile = fileURLToPath(import.meta.url);
  const entry = process.argv[1] ? path.resolve(process.argv[1]) : '';
  return Boolean(entry) && thisFile === entry;
})();

if (isMain) {
  main().catch(error => {
    console.error(colorize('❌ 测试执行失败:', 'red'), error);
    process.exit(1);
  });
}

export { runTest, testCases };
