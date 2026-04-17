const { redirectToSubpackage } = require('../../utils/subpackageRedirect');

Page({
  onLoad(options) {
    redirectToSubpackage('/packageHost/pages/freeCourseDetailsonline/freeCourseDetailsonline', options);
  }
});
