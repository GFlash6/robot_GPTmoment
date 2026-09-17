import { test,expect } from '@playwright/test';
import fs from 'node:fs';
const ids=JSON.parse(fs.readFileSync('../.runtime/ui-validation/ui-check-ids.json','utf8'));
test('actual task flow, evidence, models and resource navigation',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'让每一次执行都有迹可循.'})).toBeVisible();
 await expect(page.getByText('API 已连接',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'归档 UI 设计文档并校验完整性',exact:true}).click();
 await expect(page.getByTestId('task-flow')).toBeVisible();
 await page.locator('.react-flow__node').filter({hasText:'asset.verify'}).click();
 await expect(page.getByText('已由执行端确认',{exact:true})).toBeVisible();
 await expect(page.locator('.timeline').getByText('收到执行结果',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:`asset:${ids.asset}`,exact:true}).click();
 await expect(page.getByRole('heading',{name:'数据与记忆',exact:true})).toBeVisible();
 await expect(page.getByText('document',{exact:true}).last()).toBeVisible();
 await page.locator('nav').getByRole('button',{name:'资源占用'}).click();
 await expect(page.getByRole('heading',{name:'local-files/archive-io'})).toBeVisible();
 await expect(page.getByText('当前没有占用记录')).toBeVisible();
 await page.locator('nav').getByRole('button',{name:'模型记录'}).click();
 await expect(page.getByRole('heading',{name:'尚无模型响应记录'})).toBeVisible();
 expect(errors).toEqual([]);
});
test('actual fallback and interruption remain distinct',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'验证缺失文件失败后的真实 fallback',exact:true}).click();
 await page.locator('.react-flow__node').filter({hasText:'file.ingest'}).click();
 await expect(page.getByText('实际执行尝试 · 2',{exact:true})).toBeVisible();
 await expect(page.getByText('计划中的 fallback 候选',{exact:true})).toBeVisible();
 await page.getByRole('button').filter({hasText:'检查分块归档取消后的停止证据'}).click();
 await expect(page.locator('.control-banner')).toContainText('pause');
 await page.locator('.react-flow__node').filter({hasText:'file.copy'}).click();
 await expect(page.getByText('已由执行端确认',{exact:true})).toBeVisible();
});
test('disconnect preserves real data with stale warning',async({page,context})=>{
 await page.goto('/');await expect(page.getByText('API 已连接',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'归档 UI 设计文档并校验完整性',exact:true})).toBeVisible();
 await context.setOffline(true);
 await expect(page.getByText('数据可能过期',{exact:true})).toBeVisible({timeout:10000});
 await expect(page.getByRole('button',{name:'归档 UI 设计文档并校验完整性',exact:true})).toBeVisible();
 await context.setOffline(false);await expect(page.getByText('API 已连接',{exact:true})).toBeVisible({timeout:10000});
});
test('narrow viewport remains usable',async({page})=>{
 await page.setViewportSize({width:768,height:1024});await page.goto('/');
 await page.locator('nav').getByRole('button',{name:'任务流程'}).click();
 await expect(page.getByRole('heading',{name:'任务队列'})).toBeVisible();
 await expect(page.getByTestId('task-flow')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
