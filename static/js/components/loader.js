function setLoading() {
    $('#loadMessage').html('<img class=\'loader-emote\' src=\'/static/images/misc/umpin.apng\' />');

    $('#loadingModal').addClass('is-active');
    $('#htmlRoot').addClass('is-clipped');
}

function unsetLoading() {
    $('#loadingModal').removeClass('is-active');
    $('#htmlRoot').removeClass('is-clipped');
}
