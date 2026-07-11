function assertPackageDeeptutorDirectBillingContract(assert, billingJs, billingWxml) {
  assert(
    billingWxml.indexOf("开通学习权益") >= 0 &&
      billingWxml.indexOf("item.turns") >= 0 &&
      billingWxml.indexOf("{{item.points}}") === -1 &&
      billingWxml.indexOf("selectedPackage.points") === -1,
    "billing package surface should show promised usage counts, not internal points",
  );
  assert(
    billingWxml.indexOf("sales-contact-qr.png") < 0 &&
      billingWxml.indexOf("联系销售") < 0 &&
      billingWxml.indexOf("长按识别二维码") < 0 &&
      billingWxml.indexOf("添加销售顾问") < 0,
    "billing package surface should not expose sales QR fallback",
  );
  assert(
    billingJs.indexOf("contactSalesVisible") < 0 &&
      billingJs.indexOf("api.createBillingCheckout") >= 0 &&
      billingJs.indexOf("requestPayment") >= 0,
    "billing open action should create a WeChat checkout before requesting payment",
  );
}

module.exports = {
  assertPackageDeeptutorDirectBillingContract: assertPackageDeeptutorDirectBillingContract,
};
