const { redirectToSubpackage } = require('../../utils/subpackageRedirect');

Page({
  onLoad(options) {
    redirectToSubpackage('/packageHost/pages/dyforios/dyforios', options);
  }
});
