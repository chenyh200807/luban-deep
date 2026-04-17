const { redirectToSubpackage } = require('../../utils/subpackageRedirect');

Page({
  onLoad(options) {
    redirectToSubpackage('/packageHost/pages/getphone/getphone', options);
  }
});
