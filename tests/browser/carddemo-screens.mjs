import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { writeFile } from 'node:fs/promises';
const browser = await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:1100,height:700}});
  await page.goto(pathToFileURL(resolve('work/carddemo-data/screens/COSGN0A.html')).href);
  await page.getByRole('textbox',{name:'USERID',exact:true}).fill('USER0001');
  await page.getByLabel('PASSWD',{exact:true}).fill('PUBLIC01');
  if(await page.getByLabel('PASSWD',{exact:true}).getAttribute('type')!=='password')throw Error('password-not-masked');
  await page.screenshot({path:'work/carddemo-data/screens/signon.png',fullPage:true});
  await writeFile('work/carddemo-data/screens/browser.json',JSON.stringify({schema:'carddemo-layout-browser/1',userInputPassed:true,passwordMasked:true,scope:'static source-bound layout only',releaseAuthorized:false},null,2));
} finally {await browser.close();}
