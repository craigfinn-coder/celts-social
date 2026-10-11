/**
 * 80k page: hourly "proven winners" ping to GitHub (celts-social).
 *
 * Every hour (07:00-23:00 UK) send GitHub the posts published in the last
 * 5 hours with today's Jetpack views. GitHub (src/promote.py) picks the best
 * one and posts its card to the second Facebook page through Buffer.
 * Uses CAH_GITHUB_TOKEN / CAH_GITHUB_REPO from the "GitHub card ping" snippet.
 *
 * Admins can fire it by hand: /wp-admin/?cah_promote_now=1  (&mode=test)
 * Last result is kept in the option cah_promote_last.
 */

add_action( 'init', function () {
	if ( ! wp_next_scheduled( 'cah_promote_check' ) ) {
		wp_schedule_event( time() + 300, 'hourly', 'cah_promote_check' );
	}
} );
add_action( 'cah_promote_check', function () { cah_promote_check_run(); } );

function cah_promote_views_today() {
	$views = array();
	$data  = null;
	if ( class_exists( '\Automattic\Jetpack\Stats\WPCOM_Stats' ) ) {
		$stats = new \Automattic\Jetpack\Stats\WPCOM_Stats();
		$data  = $stats->get_top_posts( array( 'period' => 'day', 'num' => 1, 'max' => 100 ) );
	}
	if ( ! is_array( $data ) || empty( $data['days'] ) ) {
		return $views;
	}
	foreach ( $data['days'] as $day ) {
		foreach ( (array) ( $day['postviews'] ?? array() ) as $p ) {
			$id = (int) ( $p['id'] ?? 0 );
			if ( $id ) {
				$views[ $id ] = ( $views[ $id ] ?? 0 ) + (int) ( $p['views'] ?? 0 );
			}
		}
	}
	return $views;
}

function cah_promote_check_run( $mode = '', $force = false ) {
	$hour = (int) wp_date( 'G' );
	if ( ! $force && ( $hour >= 23 || $hour < 7 ) ) {
		return 'quiet hours';
	}
	if ( ! defined( 'CAH_GITHUB_TOKEN' ) || ! defined( 'CAH_GITHUB_REPO' ) ) {
		update_option( 'cah_promote_last', 'no GitHub token constants', false );
		return 'no token';
	}
	$posts = get_posts( array(
		'post_type'        => 'post',
		'post_status'      => 'publish',
		'posts_per_page'   => 40,
		'date_query'       => array( array( 'after' => '5 hours ago', 'column' => 'post_date_gmt' ) ),
		'suppress_filters' => true,
	) );
	if ( ! $posts ) {
		update_option( 'cah_promote_last', current_time( 'mysql' ) . ' no recent posts', false );
		return 'no recent posts';
	}
	$views = cah_promote_views_today();
	$cands = array();
	foreach ( $posts as $p ) {
		$cands[] = array(
			'slug'     => $p->post_name,
			'date_gmt' => str_replace( ' ', 'T', $p->post_date_gmt ),
			'link'     => get_permalink( $p ),
			'title'    => html_entity_decode( get_the_title( $p ), ENT_QUOTES ),
			'views'    => (int) ( $views[ $p->ID ] ?? 0 ),
		);
	}
	usort( $cands, function ( $a, $b ) { return $b['views'] <=> $a['views']; } );
	$payload = array( 'candidates' => array_slice( $cands, 0, 15 ) );
	if ( $mode ) {
		$payload['mode'] = $mode;
	}
	$res  = wp_remote_post( 'https://api.github.com/repos/' . CAH_GITHUB_REPO . '/dispatches', array(
		'timeout' => 15,
		'headers' => array(
			'Authorization' => 'Bearer ' . CAH_GITHUB_TOKEN,
			'Accept'        => 'application/vnd.github+json',
			'User-Agent'    => 'celtsarehere-promote',
		),
		'body'    => wp_json_encode( array( 'event_type' => 'promote-check', 'client_payload' => $payload ) ),
	) );
	$code = is_wp_error( $res ) ? $res->get_error_message() : wp_remote_retrieve_response_code( $res );
	$top  = $cands[0]['slug'] . ' ' . $cands[0]['views'];
	$msg  = current_time( 'mysql' ) . " sent " . count( $payload['candidates'] ) . " (top: $top) -> $code";
	update_option( 'cah_promote_last', $msg, false );
	return $msg;
}

add_action( 'admin_init', function () {
	if ( empty( $_GET['cah_promote_now'] ) || ! current_user_can( 'manage_options' ) ) {
		return;
	}
	$mode = sanitize_key( $_GET['mode'] ?? '' );
	wp_die( esc_html( cah_promote_check_run( $mode, true ) ), 'Promote check' );
} );
